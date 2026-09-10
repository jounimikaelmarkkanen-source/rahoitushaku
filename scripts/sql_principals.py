"""Generate Azure SQL external-user SIDs from managed identity object IDs."""
import argparse
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("collector_object_id", type=uuid.UUID)
parser.add_argument("api_object_id", type=uuid.UUID)
args = parser.parse_args()
print("COLLECTOR_SID:", args.collector_object_id.bytes_le.hex())
print("API_SID:", args.api_object_id.bytes_le.hex())
