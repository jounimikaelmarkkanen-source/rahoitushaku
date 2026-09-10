# Rahoitusrekisterin luovutus ja Azure-käyttöönotto

Ohjelmisto 0.4.0 · tietokantaskeema 0007 · aineistopoiminta 10.9.2026.

Tämä ohje on kokonaisuuden vastaanottajalle ja kaupungin IT:lle. Google Driveen toimitettava ZIP sisältää koko päivätyn aineiston, alkuperäiset asiakirjat, kokotekstit, Excelin ja tekniset ohjeet. GitHubiin toimitettava koodi sisältää kerääjän, rajapinnan, lähdeasetukset, testit ja Azure-määritykset. Tuotannon tietokanta sijoitetaan Azure SQL:ään. Päivittäinen ajo toimii käyttöönoton jälkeen kaupungin Azure-ympäristössä.

**Azure-resursseja tai päivittäistä tuotantoajoa ei ole aktivoitu tässä toimituksessa.** Azure SQL -verkkoyhteys, Entra-roolit, kapasiteetti ja Power BI / Excel -päivitys varmistetaan kaupungin tenantissa.

## 1. Anna vastaanottajalle toimituskohteet

Toimita vastaanottajalle Google Drive -kansion ja GitHub-repositorion linkit sekä GitHubiin tallennetun julkaisun commit-tunniste. Anna oikeudet nimetyille vastaanottajille organisaation käytännön mukaan. Ylläpitäjän pitää voida kloonata koodi ja lukea koko siirtopaketti. Tilien tunnuksia tai salaisuuksia ei sisällytetä luovutukseen.

| Osa | Tiedosto tai kansio | Käyttö |
|---|---|---|
| Koko siirtopaketti | `rahoitusrekisteri-microsoft.zip` | Koodi, tietokanta, kaikki viedyt alkuperäistiedostot ja kokotekstit sekä ohjeet samassa ZIP64-paketissa. |
| Paketin tarkistus | `rahoitusrekisteri-microsoft.sha256` | Varmistaa latauksen vastaavuuden toimitukseen. |
| Selattava poiminta | `rahoitusrekisteri.xlsx` | 16 069 tietuetta, 12 rahoitusryhmää, FSTP-suodatin ja hakukohtaiset asiakirjalinkit. |
| Tietokanta ZIPin sisällä | `data/funding.db` | Siirrettävä SQLite-kanta, mukana myös binääriset alkuperäiset, tekstit, versiot ja suhteet. |
| Avoimet tiedostot | `data/opportunities.csv`, `data/*.jsonl`, `data/documents/` | Käyttö muissa järjestelmissä sekä kokonaisten ehtojen avaaminen ilman palvelinta. |
| Todennus | `data/metrics.json`, `FILE-MANIFEST.json` | Tietuemäärät, tietokannan SHA-256 sekä kaikkien pakattujen tiedostojen koot ja tarkistussummat. |
| Koodi | GitHub-repositorion `src`, `config`, `migrations`, `infra`, `integrations`, `tests` | Sovelluksen ylläpito ja toistettava käyttöönotto. |

GitHub ei sisällä tuotantotietokantaa, suurta asiakirja-arkistoa, paikallista virtuaaliympäristöä tai kirjautumistietoja. GitHub-koodin ja Drive-aineiston yhteys varmistetaan samalla ohjelmisto- ja skeemaversiolla sekä luovutukseen kirjatulla commit-tunnisteella.

## 2. Lataa ja tarkista aineisto

Lataa ZIP ja sen `.sha256`-tiedosto kokonaan. Data vie purettuna tässä toimituksessa noin 31 GiB; varaa työasemalle tai käyttöönottoagentille vähintään 80 GB vapaata tilaa latausta, purkua ja käyttöönoton työtilaa varten. ZIP käyttää suuren tiedoston ZIP64-muotoa. Käytä sitä tukevaa purkuohjelmaa ja pura kansiorakenne kokonaan.

Windows PowerShell:

```powershell
Get-FileHash .\rahoitusrekisteri-microsoft.zip -Algorithm SHA256
```

Linux / macOS:

```sh
shasum -a 256 -c rahoitusrekisteri-microsoft.sha256
```

Vertaa Windowsissa tulosta `.sha256`-tiedoston arvoon. Purun jälkeen avaa Excel samasta kansiosta, jonka alla `data/documents/` sijaitsee. Tällöin Haut-välilehden asiakirjalinkit toimivat. Tarkista myös [validointiraportti](VALIDOINTI.md) ja [12 rahoitusryhmän kattavuus](PRIORITEETTILÄHTEET.md).

Jos työskentelet GitHubista kloonatussa koodikansiossa, kopioi puretun paketin `data/` sen alle. Käytä toimitusta vastaavaa commitia. `data/` on rajattu pois Git-versionhallinnasta. Kun SQL-siirto on valmis, Azure-sovellus käyttää Azure SQL:ää eikä paikallista SQLite-tiedostoa.

## 3. Sovi käyttöönoton omistajat ja asetukset

| Vastuu | Täytettävät asiat |
|---|---|
| Kaupungin rahoitusasiantuntija | Lähteiden omistajuus, kaupungin hakijarooli ja puutteiden tarkistusjono. |
| Azure-ylläpitäjä | Tenant, tilaus, resurssiryhmä, hyväksytty EU-alue, konttirekisteri, kustannusseuranta ja kapasiteetti. |
| Identiteetinhallinta | API-sovellusrekisteröinti, `Funding.Read` / `Funding.Review`, SQL:n Entra-pääkäyttäjäryhmä ja raportoinnin lukuryhmä. |
| Verkkoylläpitäjä | Yksityinen SQL-yhteys, DNS, julkaisuagentin yhteys ja Power BI / Excel -yhdyskäytävä. |
| Sovellusylläpitäjä | Koodijulkaisu, migraatiot, koeajo, päivittäinen valvonta ja palautuksen harjoittelu. |

Täytä `infra/parameters.example.json`-tiedoston kopioon `registryServer`, `registryResourceId`, `image`, `sqlAdminName`, `sqlAdminObjectId` ja `apiAudience`. Sovita `prefix`, `location` ja verkko kaupungin käytäntöihin. Korvaa kerääjän yhteystieto `.env.example`- ja Bicep-asetuksissa organisaation ylläpitoyhteystiedolla.

Pidä aluksi **`deployWorkloads=false`** ja **`enableDailySchedule=false`**. Tuotannon muuttujat ja käyttöoikeudet määritetään kaupungin järjestelmään. [Tekninen Microsoft-ohje](MICROSOFT-KAYTTOONOTTO.md) sisältää tarkat roolit ja komennot.

## 4. Rakenna sovellus ja infrastruktuurin perusta

Käytä GitHubista kloonattua, toimitukseen kirjattua commitia. Asenna käyttöönottoagentille Azure CLI, uv, Python 3.12+ ja ODBC 18. Rakenna sovelluksen Linux amd64 -kontti kaupungin ACR:ään:

```sh
az acr build --registry REGISTRY_NAME --platform linux/amd64 --image funding-registry:RELEASE_ID .
```

Kirjaa valmistuneen kuvan digest parametrin `image` arvoksi. ACR rakentaa kuvan projektin Dockerfilestä. [Microsoftin ACR-ohje](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tutorial-quick-task).

Käännä Bicep, tarkista muutossuunnitelma ja luo perusta:

```sh
az bicep build --file infra/main.bicep
az deployment group what-if --resource-group RESOURCE_GROUP --template-file infra/main.bicep --parameters @CITY_PARAMETERS.json
az deployment group create --resource-group RESOURCE_GROUP --name funding-foundation --template-file infra/main.bicep --parameters @CITY_PARAMETERS.json deployWorkloads=false enableDailySchedule=false
```

Kirjaa deploymentin outputit: SQL-palvelin, hallittujen identiteettien tunnisteet ja tarvittavat ympäristötiedot. Anna kerääjän ja API:n identiteeteille `AcrPull` vain kyseiseen rekisteriin. Esimerkin SQL S0 on lähtöasetus; varsinainen taso valitaan täyden aineiston siirto- ja kuormituskokeella.

## 5. Siirrä tietokanta tyhjään Azure SQL -kohteeseen

Tee siirto hyväksytystä yksityisestä verkosta SQL:n Entra-pääkäyttäjän oikeuksilla. Azure SQL käyttää Entra-tunnistautumista, ja tuotantosovellukset hallittuja identiteettejä. [Microsoftin Entra SQL -ohje](https://learn.microsoft.com/en-us/azure/azure-sql/database/authentication-aad-overview).

```sh
uv sync --frozen --extra azure
export FUNDING_AZURE_SQL_SERVER=YOUR_SERVER.database.windows.net
export FUNDING_AZURE_SQL_DATABASE=funding
uv run alembic upgrade head
uv run funding transfer --from-url sqlite:///data/funding.db
```

Komennot käyttävät Bash-syntaksia. PowerShellissa aseta samat muuttujat muodossa `$env:FUNDING_AZURE_SQL_SERVER="..."`; `uv`-komennot ovat samat. Älä aseta käyttöönottoagentille sovelluksen hallitun identiteetin client ID:tä: migraatio ja siirto käyttävät kirjautunutta Entra-ylläpitäjää.

**Älä aja `funding init` ennen toimitetun aineiston siirtoa.** Se täyttäisi lähdetaulun, ja siirto hyväksyy vain tyhjät kohdetaulut samassa skeemaversiossa. Siirrä tietokanta kerääjän ollessa pysäytettynä. Toiminto säilyttää myös alkuperäistiedostot, kokotekstit, versiot, lähdeviitteet ja arviot.

Vertaa siirron jälkeen kaikkien taulujen määriä `data/metrics.json`-tiedoston `table_counts`-osioon. Tarkista lisäksi otannalla haku, pitkä kokoteksti ja alkuperäistiedoston tarkistussumma. Tässä toimituksessa on muun muassa 16 069 hakutietuetta, 47 298 sisältöversiota ja 2 901 150 haun ja asiakirjan suhderiviä. Pelkkä hakutaulun rivimäärä ei riitä koko siirron todentamiseen.

Suorita `scripts/sql_principals.py` ja täytä sen tuloksilla `infra/bootstrap.sql`. Skripti luo kerääjän ja API:n rajatut SQL-oikeudet. Lisää raportointiryhmä lukurooliin teknisen ohjeen mukaisesti.

## 6. Julkaise API ja tee koeajo

```sh
az deployment group create --resource-group RESOURCE_GROUP --name funding-workloads --template-file infra/main.bicep --parameters @CITY_PARAMETERS.json deployWorkloads=true enableDailySchedule=false
az containerapp job start --resource-group RESOURCE_GROUP --name PREFIX-collect
```

Koeajon hyväksymisehdot:

1. API avautuu oikealla Entra-tokenilla; puuttuva rooli ja väärä tenant hylätään. Luku- ja arviointioikeudet toimivat sovitusti.
2. `/v1/priorities` palauttaa 12 ryhmää; `priority=8`, `cascade=true` ja `record_kind=advance_information` rajaavat oikeat tietueet.
3. Kokoteksti ja alkuperäinen asiakirja saadaan kokonaisina. Arvion tallennus säilyttää version ja muutoslokin.
4. Keruu päivittää havaintoajat, jatkaa asiakirjajonoa ja näyttää lähdevirheet. MYR:n päätöspalvelun, Nordenin ja Varken tunnetut katveet käsitellään nimettyinä ylläpitotehtävinä.
5. Power BI / Excel saa yhteyden SQL:ään hyväksytyn verkon kautta. Päivitys toimii myös ajastettuna organisaation ympäristössä.
6. Täysi aineisto mahtuu valittuun kapasiteettiin ja koeajo valmistuu aikarajassa. Palautus varmistuksesta on kokeiltu uuteen tietokantaan.

`funding daily --require-all` ilmoittaa myös yksittäisen lähteen puutteesta epäonnistumisena. Nykyiset lähdekatveet eivät häviä Azureen siirtämällä. Ylläpitäjä erottaa tunnetun lähdevirheen koko keruun pysähtymisestä.

## 7. Liitä Microsoft-työkalut ja käynnistä päivittäinen ajo

Ota `integrations/PowerQuery-AzureSQL.m` käyttöön ja vaihda palvelin sekä tietokanta. `PowerQuery-Priorities.m` tuottaa 12 ryhmän liitostaulun samasta `config/priorities.json`-määrityksestä kuin API. Määritä JSON-tiedoston ylläpidetty sijainti ja pilvipäivityksen yhteys teknisen ohjeen mukaan. `PowerQuery-Documents.m` ja `PowerQuery-DocumentText.m` tuovat asiakirjaviitteet ja numeroidut kokotekstiosat erillisinä tauluina.

Asiakirjakytkentöjen aineisto ylittää Excel-laskentataulukon rivirajan. Käytä tietomallia tai rajattua hakukohtaista kyselyä. Pidä lähteen tuoreus, ehtoaineiston tila ja hakukelpoisuuden tarkistus näkyvissä raportissa.

Käynnistä hyväksytyn koeajon jälkeen päivittäinen ajo:

```sh
az deployment group create --resource-group RESOURCE_GROUP --name funding-daily --template-file infra/main.bicep --parameters @CITY_PARAMETERS.json deployWorkloads=true enableDailySchedule=true
```

Ajastus on joka päivä klo **03.00 UTC**, Suomessa talvella 05.00 ja kesällä 06.00. Container Apps Jobs tulkitsee ajastuksen UTC-aikana. [Microsoftin Jobs-ohje](https://learn.microsoft.com/en-us/azure/container-apps/jobs).

## 8. Ylläpidä ja luovuta vastuu

Kirjaa käyttöönottopäivä, julkaistu commit ja image digest, Drive-poiminnan tarkistussumma, Azure-resurssit, omistajat sekä palautustestin tulos kaupungin ylläpitodokumentaatioon. Säilytä muuttumaton päivätty Drive-toimitus. Koodin seuraavat versiot julkaistaan GitHubin kautta ja testataan ennen käyttöönottoa.

Päivittäin seurataan ajoa, yli 36 tunnin ikäisiä lähteitä ja lähestyviä määräaikoja. Viikoittain rahoitusasiantuntija käsittelee kelpoisuus- ja sisältöpuutteiden jonon. Lähdeasetusten muutos otetaan käyttöön komennolla `funding sync-sources`. Tekoälyratkaisut voidaan liittää myöhemmin SQL-näkymiin tai rajapintaan omalla lukuidentiteetillään.

Jatkossa tarvittavat ohjeet: [Microsoft-käyttöönotto](MICROSOFT-KAYTTOONOTTO.md), [tietomalli ja ylläpito](TIETOMALLI-JA-YLLAPITO.md), [ehdot ja liitteet](EHDOT-JA-LIITTEET.md), [lähdekattavuus](RAHOITTAJAT-JA-KATTAVUUS.md) ja [validointi](VALIDOINTI.md).
