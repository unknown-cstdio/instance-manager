from time import sleep
import boto3
import pandas as pd
import numpy as np
import datetime
import urllib.request, json 
from typing import List, Dict

US_REGIONS = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']

ec2 = boto3.client('ec2')
ce = boto3.client('ce')

def get_instance_type(types):
    response = ec2.describe_instance_types(
        InstanceTypes=types
    )
    return response

def update_spot_prices():
    responses = ec2.describe_spot_price_history(
        ProductDescriptions=['Linux/UNIX'],
        StartTime=datetime.datetime.utcnow(),
    )
    spot_prices: List[Dict[str, str]] = []
    #get instance types in a batch of 50
    item_count = len(responses['SpotPriceHistory'])
    batch_size = 100
    type_to_NIC = {}
    for i in range(0, item_count, batch_size):
        batch = responses['SpotPriceHistory'][i:i+batch_size]
        instance_types = []
        for response in batch:
            instance_types.append(response['InstanceType'])
        #get instance types
        instance_types_response = ec2.describe_instance_types(
            InstanceTypes=instance_types
        )
        #add instance types to spot price history
        for response in instance_types_response['InstanceTypes']:
            type_to_NIC[response['InstanceType']] = response['NetworkInfo']['MaximumNetworkInterfaces']
    #add price per interface to spot price history
    for response in responses['SpotPriceHistory']:
        spot_prices.append({
            'AvailabilityZone': response['AvailabilityZone'],
            'InstanceType': response['InstanceType'],
            'MaximumNetworkInterfaces': type_to_NIC[response['InstanceType']],
            'SpotPrice': response['SpotPrice'],
            'PricePerInterface': (float(response['SpotPrice']) + 0.005 * (type_to_NIC[response['InstanceType']] - 1)) / type_to_NIC[response['InstanceType']],
            'Timestamp': response['Timestamp']  
        })
    df = pd.DataFrame(spot_prices)
    #write to csv
    df.to_csv('spot_prices.csv')
    return df

def update_azure_prices():
    next_page_link = "https://prices.azure.com/api/retail/prices?$skip=0&$filter=serviceName%20eq%20%27Virtual%20Machines%27%20and%20priceType%20eq%20%27Consumption%27%20and%20armRegionName%20eq%20%27eastus%27"
    spot_prices: List[Dict[str, str]] = []
    while next_page_link != None:
        with urllib.request.urlopen(next_page_link) as url:
            data = json.loads(url.read().decode())
            for item in data['Items']:
                if 'Spot' in item['skuName']:
                    spot_prices.append({
                        'AvailabilityZone': item['location'],
                        'InstanceType': item['skuName'],
                        'MaximumNetworkInterfaces': 1,
                        'SpotPrice': item['retailPrice'],
                        'PricePerInterface': item['retailPrice'],
                        'Timestamp': item['effectiveStartDate']  
                    })
            next_page_link = data['NextPageLink']
    df = pd.DataFrame(spot_prices)
    #write to csv
    df.to_csv('azure_spot_prices.csv')
    return df

def get_spot_prices():
    df = pd.read_csv('spot_prices.csv')
    return df

def get_all_instances():
    response = ec2.describe_instances()
    return response

def get_specific_instances(instance_ids):
    response = ec2.describe_instances(
        InstanceIds=instance_ids
    )
    return response

def start_instances(instance_ids):
    response = ec2.start_instances(
        InstanceIds=instance_ids
    )
    return response

def stop_instances(instance_ids):
    response = ec2.stop_instances(
        InstanceIds=instance_ids
    )
    return response

def reboot_instances(instance_ids):
    response = ec2.reboot_instances(
        InstanceIds=instance_ids
    )
    return response

def terminate_instances(instance_ids):
    response = ec2.terminate_instances(
        InstanceIds=instance_ids
    )
    return response

def create_fleet(instance_type, region, launch_template, num):
    response = ec2.create_fleet(
        SpotOptions={
            'AllocationStrategy': 'lowestPrice',
        },
        LaunchTemplateConfigs=[
            {
                'LaunchTemplateSpecification': {
                    'LaunchTemplateId': launch_template,
                    'Version': '1'
                },
                'Overrides': [
                    {
                        'InstanceType': instance_type,
                        'AvailabilityZone': region
                    }
                ]
            }
        ],
        TargetCapacitySpecification={
            'TotalTargetCapacity': num,
            'OnDemandTargetCapacity': 0,
            'SpotTargetCapacity': num,
            'DefaultTargetCapacityType': 'spot'
        },
        Type='request',
    )
    return response

def get_cost(StartTime, EndTime):
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': StartTime,
            'End': EndTime
        },
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'SERVICE'
            },
        ]
    )
    return response

def get_addresses():
    response = ec2.describe_addresses()
    return response

def allocate_address():
    response = ec2.allocate_address(
        Domain='vpc'
    )
    return response

def release_address(allocation_id):
    response = ec2.release_address(
        AllocationId=allocation_id
    )
    return response

def associate_address(instance_id, allocation_id, network_interface_id):
    response = ec2.associate_address(
        InstanceId=instance_id,
        AllocationId=allocation_id,
        NetworkInterfaceId=network_interface_id
    )
    return response

def disassociate_address(association_id):
    response = ec2.disassociate_address(
        AssociationId=association_id
    )
    return response

update_azure_prices()

#spot_prices = get_spot_prices()

#sort by price
#spot_prices = spot_prices.sort_values(by=['PricePerInterface'])

# create the cheapest fleet
#cheapest = spot_prices.iloc[0]
#print(cheapest)

#cost = get_cost('2023-01-02', '2023-01-03')
#print(cost)
#print(get_instance_types(cheapest['InstanceType'])['InstanceTypes'][0]['NetworkInfo']['MaximumNetworkInterfaces'])

#print(cheapest['InstanceType'])
#print(x86_instance_types)
#print(cheapest)

#x86: lt-04d9c8ac5d00a2078
#arm: lt-0abc44b6c12879596
#response = create_fleet("t3a.medium", "us-east-1c", 'lt-04d9c8ac5d00a2078')
#response = create_fleet("m6gd.medium", "us-east-1f", 'lt-0abc44b6c12879596')
#print(response)
#print('instances created')




