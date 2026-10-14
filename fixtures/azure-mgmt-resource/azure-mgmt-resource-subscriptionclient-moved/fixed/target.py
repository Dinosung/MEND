from azure.mgmt.resource.subscriptions import SubscriptionClient


def enabled_subscriptions(credential):
    """Map subscription id -> display name for every enabled subscription we can see."""
    client = SubscriptionClient(credential)
    return {s.subscription_id: s.display_name for s in client.subscriptions.list() if s.state == "Enabled"}
