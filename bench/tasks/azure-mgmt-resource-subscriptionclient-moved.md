<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our cost report needs the list of Azure subscriptions the service principal can see. Please
write `target.py` with `enabled_subscriptions(credential)`, where `credential` is an Azure
credential object we pass in (for example a `DefaultAzureCredential`): use the Azure
management SDK to list the subscriptions and return a dict mapping subscription id to display
name, including only subscriptions whose state is `Enabled`.
