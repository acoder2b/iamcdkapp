import boto3
import yaml

def list_aws_accounts():
    client = boto3.client('organizations')
    paginator = client.get_paginator('list_accounts')
    
    accounts = []
    
    for page in paginator.paginate():
        for account in page['Accounts']:
            account_info = {
                'Id': account['Id'],
                'Name': account['Name'],
                'Email': account['Email'],
                'Status': account['Status'],
                'JoinedMethod': account['JoinedMethod'],
                'JoinedTimestamp': account['JoinedTimestamp'].isoformat(),
            }
            accounts.append(account_info)
    
    return accounts

def dump_to_yaml(accounts, filename='aws_accounts.yaml'):
    with open(filename, 'w') as file:
        yaml.dump(accounts, file, default_flow_style=False, sort_keys=False)

if __name__ == "__main__":
    accounts = list_aws_accounts()
    dump_to_yaml(accounts)
    print(f"Accounts information dumped into 'aws_accounts.yaml'")
