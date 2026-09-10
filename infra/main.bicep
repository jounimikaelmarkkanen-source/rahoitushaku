targetScope = 'resourceGroup'

@description('Unique lowercase resource prefix, 3-14 characters.')
@minLength(3)
@maxLength(14)
param prefix string
param location string = resourceGroup().location
@description('Existing private ACR login server, for example name.azurecr.io.')
param registryServer string
@description('Existing ACR resource ID. Grant AcrPull to both identities before the workloads deployment.')
param registryResourceId string
@description('Immutable container image reference, preferably repository@sha256:digest.')
param image string
@description('Entra tenant ID.')
param tenantId string = subscription().tenantId
@description('Entra group object ID for SQL administrators.')
param sqlAdminObjectId string
param sqlAdminName string
@description('Client ID of the single-tenant Entra API app registration (v2 access tokens).')
param apiAudience string
@description('Deploy foundation first, then migrate/bootstrap SQL, then set true.')
param deployWorkloads bool = false
@description('Schedule must be explicitly enabled after a successful manual acceptance run.')
param enableDailySchedule bool = false
param apiExternal bool = true
param userAgent string = 'MunicipalFundingRegistry/0.4 (public funding monitoring)'

var sqlName = '${prefix}-sql-${uniqueString(resourceGroup().id)}'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${prefix}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.64.0.0/16'] }
    subnets: [
      {
        name: 'container-apps'
        properties: {
          addressPrefix: '10.64.0.0/23'
          delegations: [{ name: 'container-apps', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
      { name: 'private-endpoints', properties: { addressPrefix: '10.64.2.0/24', privateEndpointNetworkPolicies: 'Disabled' } }
    ]
  }
}

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: '${prefix}-environment'
  location: location
  properties: {
    vnetConfiguration: { infrastructureSubnetId: '${network.id}/subnets/container-apps' }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: workspace.properties.customerId, sharedKey: workspace.listKeys().primarySharedKey }
    }
  }
}

resource collectorIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-collector'
  location: location
}
resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-api'
  location: location
}

resource sql 'Microsoft.Sql/servers@2023-08-01' = {
  name: sqlName
  location: location
  properties: {
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true
      principalType: 'Group'
      login: sqlAdminName
      sid: sqlAdminObjectId
      tenantId: tenantId
    }
  }
}
resource database 'Microsoft.Sql/servers/databases@2023-08-01' = {
  parent: sql
  name: 'funding'
  location: location
  sku: { name: 'S0', tier: 'Standard' }
  properties: { collation: 'Finnish_Swedish_100_CI_AS_SC', maxSizeBytes: 268435456000, requestedBackupStorageRedundancy: 'Local' }
}
resource retention 'Microsoft.Sql/servers/databases/backupShortTermRetentionPolicies@2023-08-01' = {
  parent: database
  name: 'default'
  properties: { retentionDays: 14 }
}
resource dns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink${az.environment().suffixes.sqlServerHostname}'
  location: 'global'
}
resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dns
  name: '${prefix}-sql-dns'
  location: 'global'
  properties: { registrationEnabled: false, virtualNetwork: { id: network.id } }
}
resource endpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${prefix}-sql-private'
  location: location
  properties: {
    subnet: { id: '${network.id}/subnets/private-endpoints' }
    privateLinkServiceConnections: [{
      name: 'sql'
      properties: { privateLinkServiceId: sql.id, groupIds: ['sqlServer'] }
    }]
  }
}
resource zoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: endpoint
  name: 'default'
  properties: { privateDnsZoneConfigs: [{ name: 'sql', properties: { privateDnsZoneId: dns.id } }] }
}

var commonEnv = [
  { name: 'FUNDING_AZURE_SQL_SERVER', value: sql.properties.fullyQualifiedDomainName }
  { name: 'FUNDING_AZURE_SQL_DATABASE', value: database.name }
  { name: 'FUNDING_USER_AGENT', value: userAgent }
]

resource api 'Microsoft.App/containerApps@2025-01-01' = if (deployWorkloads) {
  name: '${prefix}-api'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${apiIdentity.id}': {} } }
  properties: {
    environmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: apiExternal, targetPort: 8000, allowInsecure: false, transport: 'auto' }
      registries: [{ server: registryServer, identity: apiIdentity.id }]
    }
    template: {
      containers: [{
        name: 'api'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: concat(commonEnv, [
          { name: 'FUNDING_MANAGED_IDENTITY_CLIENT_ID', value: apiIdentity.properties.clientId }
          { name: 'FUNDING_AUTH_MODE', value: 'entra' }
          { name: 'FUNDING_ENTRA_TENANT_ID', value: tenantId }
          { name: 'FUNDING_ENTRA_AUDIENCE', value: apiAudience }
        ])
        probes: [
          { type: 'Liveness', httpGet: { path: '/health/live', port: 8000 }, initialDelaySeconds: 20, periodSeconds: 30 }
          { type: 'Readiness', httpGet: { path: '/health/ready', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 15 }
        ]
      }]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
}

resource collector 'Microsoft.App/jobs@2025-01-01' = if (deployWorkloads) {
  name: '${prefix}-collect'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${collectorIdentity.id}': {} } }
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: enableDailySchedule ? 'Schedule' : 'Manual'
      replicaTimeout: 21600
      replicaRetryLimit: 1
      registries: [{ server: registryServer, identity: collectorIdentity.id }]
      scheduleTriggerConfig: enableDailySchedule ? { cronExpression: '0 3 * * *', parallelism: 1, replicaCompletionCount: 1 } : null
      manualTriggerConfig: enableDailySchedule ? null : { parallelism: 1, replicaCompletionCount: 1 }
    }
    template: {
      containers: [{
        name: 'collector'
        image: image
        command: ['funding']
        args: ['daily', '--require-all']
        resources: { cpu: 1, memory: '2Gi' }
        env: concat(commonEnv, [{ name: 'FUNDING_MANAGED_IDENTITY_CLIENT_ID', value: collectorIdentity.properties.clientId }])
      }]
    }
  }
}

output sqlServer string = sql.properties.fullyQualifiedDomainName
output databaseName string = database.name
output collectorPrincipalId string = collectorIdentity.properties.principalId
output collectorClientId string = collectorIdentity.properties.clientId
output apiPrincipalId string = apiIdentity.properties.principalId
output apiClientId string = apiIdentity.properties.clientId
output registryId string = registryResourceId
output networkId string = network.id
output apiUrl string = deployWorkloads ? 'https://${api!.properties.configuration.ingress.fqdn}' : ''
