from time import sleep
import boto3
import pandas as pd
import numpy as np
import datetime
import urllib.request, json 
from typing import List, Dict

US_REGIONS = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']

my_session = boto3.session.Session(profile_name='spotproxy-pat-umich-role')
ec2 = my_session.client('ec2')
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
    # response['Reservations'][0]['Instances'][0]['InstanceId']
    instance_ids = [instance['InstanceId'] for instance in response['Reservations'][0]['Instances']]
    return instance_ids

def get_specific_instances(instance_ids):
    response = ec2.describe_instances(
        InstanceIds=instance_ids
    )
    return response

def get_specific_instances_with_fleet_id_tag(fleet_id):
    """
        tag:<key> - The key/value combination of a tag assigned to the resource. Use the tag key in the filter name and the tag value as the filter value. For example, to find all resources that have a tag with the key Owner and the value TeamA, specify tag:Owner for the filter name and TeamA for the filter value.
    """
    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'tag:aws:ec2:fleet-id',
                'Values': [
                    fleet_id
                ]
            }
        ]
    )
    instance_ids = [instance['InstanceId'] for instance in response['Reservations'][0]['Instances']]
    return instance_ids

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

def create_fleet2(instance_type, region, launch_template, num):

    response = ec2.create_fleet(
        # DryRun=True|False,
        # ClientToken='string',
        SpotOptions={
            'AllocationStrategy': 'lowest-price',
            # 'MaintenanceStrategies': {
            #     'CapacityRebalance': {
            #         'ReplacementStrategy': 'launch'|'launch-before-terminate',
            #         'TerminationDelay': 123
            #     }
            # },
            # 'InstanceInterruptionBehavior': 'stop',
            # 'InstancePoolsToUseCount': 123,
            # 'SingleInstanceType': True|False,
            # 'SingleAvailabilityZone': True|False,
            # 'MinTargetCapacity': 123,
            # 'MaxTotalPrice': 'string'
        },
        # OnDemandOptions={
        #     'AllocationStrategy': 'lowest-price',
        #     # 'CapacityReservationOptions': {
        #     #     'UsageStrategy': 'use-capacity-reservations-first'
        #     # },
        #     # 'SingleInstanceType': True|False,
        #     # 'SingleAvailabilityZone': True|False,
        #     # 'MinTargetCapacity': 123,
        #     # 'MaxTotalPrice': 'string'
        # },
        # ExcessCapacityTerminationPolicy='no-termination'|'termination',
        LaunchTemplateConfigs=[
            {
                'LaunchTemplateSpecification': {
                    'LaunchTemplateId': 'lt-07c37429821503fca',
                    # 'LaunchTemplateName': 'string',
                    'Version': '1'
                },
                'Overrides': [
                    {
                        # 'InstanceType': 'a1.medium',
                        # 'MaxPrice': 'string',
                        # 'SubnetId': 'subnet-0925791c09f3d6792',
                        # 'AvailabilityZone': 'us-east-1e',
                        # 'WeightedCapacity': 123.0,
                        # 'Priority': 123.0,
                        # 'Placement': {
                        #     'AvailabilityZone': 'string',
                        #     'Affinity': 'string',
                        #     'GroupName': 'string',
                        #     'PartitionNumber': 123,
                        #     'HostId': 'string',
                        #     'Tenancy': 'default'|'dedicated'|'host',
                        #     'SpreadDomain': 'string',
                        #     'HostResourceGroupArn': 'string',
                        #     'GroupId': 'string'
                        # },
                        'InstanceRequirements': {
                            'VCpuCount': {
                                'Min': 1,
                                'Max': 10
                            },
                            'MemoryMiB': {
                                'Min': 2,
                                'Max': 10
                            },
                            # 'CpuManufacturers': [
                            #     'intel'|'amd'|'amazon-web-services',
                            # ],
                            # 'MemoryGiBPerVCpu': {
                            #     'Min': 123.0,
                            #     'Max': 123.0
                            # },
                            # 'ExcludedInstanceTypes': [
                            #     'string',
                            # ],
                            # 'InstanceGenerations': [
                            #     'current'|'previous',
                            # ],
                            # 'SpotMaxPricePercentageOverLowestPrice': 123,
                            # 'OnDemandMaxPricePercentageOverLowestPrice': 123,
                            # 'BareMetal': 'included'|'required'|'excluded',
                            # 'BurstablePerformance': 'included'|'required'|'excluded',
                            # 'RequireHibernateSupport': True|False,
                            # 'NetworkInterfaceCount': {
                            #     'Min': 123,
                            #     'Max': 123
                            # },
                            # 'LocalStorage': 'included'|'required'|'excluded',
                            # 'LocalStorageTypes': [
                            #     'hdd'|'ssd',
                            # # ],
                            # 'TotalLocalStorageGB': {
                            #     'Min': 123.0,
                            #     'Max': 123.0
                            # },
                            # 'BaselineEbsBandwidthMbps': {
                            #     'Min': 123,
                            #     'Max': 123
                            # },
                            # 'AcceleratorTypes': [
                            #     'gpu'|'fpga'|'inference',
                            # ],
                            # 'AcceleratorCount': {
                            #     'Min': 123,
                            #     'Max': 123
                            # },
                            # 'AcceleratorManufacturers': [
                            #     'amazon-web-services'|'amd'|'nvidia'|'xilinx'|'habana',
                            # ],
                            # 'AcceleratorNames': [
                            #     'a100'|'inferentia'|'k520'|'k80'|'m60'|'radeon-pro-v520'|'t4'|'vu9p'|'v100'|'a10g'|'h100'|'t4g',
                            # ],
                            # 'AcceleratorTotalMemoryMiB': {
                            #     'Min': 123,
                            #     'Max': 123
                            # },
                            # 'NetworkBandwidthGbps': {
                            #     'Min': 123.0,
                            #     'Max': 123.0
                            # },
                            # 'AllowedInstanceTypes': [
                            #     'string',
                            # ]
                        },
                        # 'ImageId': 'string'
                    },
                ]
            },
        ],
        TargetCapacitySpecification={
            'TotalTargetCapacity': 2,
            'OnDemandTargetCapacity': 0,
            'SpotTargetCapacity': 2,
            'DefaultTargetCapacityType': 'spot',
            # 'TargetCapacityUnitType': 'vcpu'|'memory-mib'|'units'
        },
        # TerminateInstancesWithExpiration=True|False,
        Type='request',
        # ValidFrom=datetime(2015, 1, 1),
        # ValidUntil=datetime(2015, 1, 1),
        # ReplaceUnhealthyInstances=True|False,
        # TagSpecifications=[
        #     {
        #         'ResourceType': 'capacity-reservation'|'client-vpn-endpoint'|'customer-gateway'|'carrier-gateway'|'coip-pool'|'dedicated-host'|'dhcp-options'|'egress-only-internet-gateway'|'elastic-ip'|'elastic-gpu'|'export-image-task'|'export-instance-task'|'fleet'|'fpga-image'|'host-reservation'|'image'|'import-image-task'|'import-snapshot-task'|'instance'|'instance-event-window'|'internet-gateway'|'ipam'|'ipam-pool'|'ipam-scope'|'ipv4pool-ec2'|'ipv6pool-ec2'|'key-pair'|'launch-template'|'local-gateway'|'local-gateway-route-table'|'local-gateway-virtual-interface'|'local-gateway-virtual-interface-group'|'local-gateway-route-table-vpc-association'|'local-gateway-route-table-virtual-interface-group-association'|'natgateway'|'network-acl'|'network-interface'|'network-insights-analysis'|'network-insights-path'|'network-insights-access-scope'|'network-insights-access-scope-analysis'|'placement-group'|'prefix-list'|'replace-root-volume-task'|'reserved-instances'|'route-table'|'security-group'|'security-group-rule'|'snapshot'|'spot-fleet-request'|'spot-instances-request'|'subnet'|'subnet-cidr-reservation'|'traffic-mirror-filter'|'traffic-mirror-session'|'traffic-mirror-target'|'transit-gateway'|'transit-gateway-attachment'|'transit-gateway-connect-peer'|'transit-gateway-multicast-domain'|'transit-gateway-policy-table'|'transit-gateway-route-table'|'transit-gateway-route-table-announcement'|'volume'|'vpc'|'vpc-endpoint'|'vpc-endpoint-connection'|'vpc-endpoint-service'|'vpc-endpoint-service-permission'|'vpc-peering-connection'|'vpn-connection'|'vpn-gateway'|'vpc-flow-log'|'capacity-reservation-fleet'|'traffic-mirror-filter-rule'|'vpc-endpoint-connection-device-type'|'verified-access-instance'|'verified-access-group'|'verified-access-endpoint'|'verified-access-policy'|'verified-access-trust-provider'|'vpn-connection-device-type'|'vpc-block-public-access-exclusion'|'ipam-resource-discovery'|'ipam-resource-discovery-association'|'instance-connect-endpoint',
        #         'Tags': [
        #             {
        #                 'Key': 'string',
        #                 'Value': 'string'
        #             },
        #         ]
        #     },
        # ],
        # Context='string'
    )
    return response

def create_fleet3(instance_type, region, launch_template, num):
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
        # TagSpecifications=[
        #     {
        #         'Tags': [
        #             {
        #                 'Key': 'fleet-id',
        #                 'Value': fleet_id_tag # this is a string
        #             },
        #         ]
        #     },
        # ],
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
# response = create_fleet("t3a.medium", "us-east-1c", 'lt-04d9c8ac5d00a2078', 2)
# response = create_fleet("m6gd.medium", "us-east-1f", 'lt-0abc44b6c12879596', 2)
# response = get_all_instances()
response = create_fleet("t2.micro", "us-east-1c", 'lt-07c37429821503fca', 2) # verified working
# response = create_fleet2("t2.micro", "us-east-1c", 'lt-07c37429821503fca', 2) # not working yet
instance_ids = get_specific_instances_with_fleet_id_tag('fleet-4da19c85-1000-4883-a480-c0b7a34b444b')
print(instance_ids)
# for i in instance_ids:
#     response = terminate_instances([i])
#     print(response)
#print('instances created')