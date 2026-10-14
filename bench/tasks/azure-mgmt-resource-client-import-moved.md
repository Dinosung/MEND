<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We are writing an inventory script for our Azure estate. Please write `target.py` with
`resource_group_locations(credential, subscription_id)`, where `credential` is an Azure
credential object we pass in (for example a `DefaultAzureCredential`): use the Azure
management SDK for resource groups to list every resource group in the subscription and
return a dict mapping each resource group name to its region (e.g.
`{"rg-web": "westeurope"}`).
