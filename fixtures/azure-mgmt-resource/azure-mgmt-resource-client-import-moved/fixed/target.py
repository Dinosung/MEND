from azure.mgmt.resource.resources import ResourceManagementClient


def resource_group_locations(credential, subscription_id):
    """Map each resource group name in the subscription to its Azure region."""
    client = ResourceManagementClient(credential, subscription_id)
    return {group.name: group.location for group in client.resource_groups.list()}
