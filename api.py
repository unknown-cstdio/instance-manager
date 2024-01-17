from time import sleep
import boto3
import pandas as pd
import numpy as np
import datetime
import urllib.request, json 
import requests
import adal
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Dict
import sys
from collections import defaultdict 

US_REGIONS = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']
INSTANCE_MANAGER_INSTANCE_ID = "i-035f88ca820e399e7"

def choose_session(is_UM_AWS, region):
    if is_UM_AWS:
        my_session = boto3.session.Session(profile_name='spotproxy-pat-umich-role')
        ec2 = my_session.client('ec2', region)
        ce = my_session.client('ce')
    else:
        ec2 = boto3.client('ec2', region)
        ce = boto3.client('ce')
    return ec2, ce

ec2, ce = choose_session(is_UM_AWS=True, region=US_REGIONS[0]) # Set this to false if you're not using UM AWS

def get_azure_token():
    tenant = "baf0d65c-c774-4040-a1a6-0ff03fd61dd6"
    client_id = "b1ccd7c7-3a4f-442b-a7cd-a32d230c9027"
    secret = "7ah8Q~noLahye3SSl~HjLVpo.DdojpGe2Sl36dll"
    authority_url = 'https://login.microsoftonline.com/'+tenant
    context = adal.AuthenticationContext(authority_url)
    token = context.acquire_token_with_client_credentials(
        resource = 'https://management.azure.com/',
        client_id = client_id,
        client_secret = secret
    )
    return token['accessToken']

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

def update_azure_vm_sizes():
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IjVCM25SeHRRN2ppOGVORGMzRnkwNUtmOTdaRSIsImtpZCI6IjVCM25SeHRRN2ppOGVORGMzRnkwNUtmOTdaRSJ9.eyJhdWQiOiJodHRwczovL21hbmFnZW1lbnQuY29yZS53aW5kb3dzLm5ldCIsImlzcyI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0L2JhZjBkNjVjLWM3NzQtNDA0MC1hMWE2LTBmZjAzZmQ2MWRkNi8iLCJpYXQiOjE3MDUwMDUwMDEsIm5iZiI6MTcwNTAwNTAwMSwiZXhwIjoxNzA1MDA5MjM4LCJhY3IiOiIxIiwiYWlvIjoiQVdRQW0vOFZBQUFBQyt5bVpJdTNxdU01TUk5V3c4ZnlrODcrQ3JaY2duTG1FV0JZUUVRRkczR3NCWUROSEZ0S3BuSDhJcWlEbWVYUC9WRGF4VnVWdkIwOTV0VVpBdDVzYmE1NzJYSkE0UFJ3bElXeFByTHZUVjRPQk9aMWZFMHZSWlVxdk84dnZ6NDkiLCJhbXIiOlsicHdkIl0sImFwcGlkIjoiMThmYmNhMTYtMjIyNC00NWY2LTg1YjAtZjdiZjJiMzliM2YzIiwiYXBwaWRhY3IiOiIwIiwiZmFtaWx5X25hbWUiOiJQZWkiLCJnaXZlbl9uYW1lIjoiSmlueXUiLCJncm91cHMiOlsiYmVjZWJlNTUtOTBhZi00ZjAzLWFiNjUtYjE3ZGYyMDVjOGRjIiwiMGY5OTJkN2UtMDMxYS00M2Y0LWJjZmQtMmU0YzMwMzY5YWMwIiwiMmU3ZGZjZjQtNzBlOC00MGQxLWJkNjktNDMyMjJlYjgwOGEyIl0sImlkdHlwIjoidXNlciIsImlwYWRkciI6IjE2OC41LjE4NS4yNiIsIm5hbWUiOiJKaW55dSBQZWkiLCJvaWQiOiJhZmQ2YjA1Zi1jYzA2LTQzZmUtOGVjMy1hZTkwMWUwNGFjMDciLCJvbnByZW1fc2lkIjoiUy0xLTUtMjEtMzk4MTcxODI5Mi0zMTQ3MDE3NDM3LTI0NTU3MjQyOTctMjU2OTMxIiwicHVpZCI6IjEwMDMyMDAwRDY4QjkzREEiLCJyaCI6IjAuQVZrQVhOYnd1blRIUUVDaHBnX3dQOVlkMWtaSWYza0F1dGRQdWtQYXdmajJNQk5aQVBFLiIsInNjcCI6InVzZXJfaW1wZXJzb25hdGlvbiIsInN1YiI6ImZwSU1zUGo2TGpxMHhOQ1FVTEM3NzlnVy1GQ3poWDV0Rk9hTTZzOVA2WTgiLCJ0aWQiOiJiYWYwZDY1Yy1jNzc0LTQwNDAtYTFhNi0wZmYwM2ZkNjFkZDYiLCJ1bmlxdWVfbmFtZSI6ImpwOTVAcmljZS5lZHUiLCJ1cG4iOiJqcDk1QHJpY2UuZWR1IiwidXRpIjoiUnVyNllqQ3lyVTJFV1Q0RmFMby1BQSIsInZlciI6IjEuMCIsIndpZHMiOlsiYjc5ZmJmNGQtM2VmOS00Njg5LTgxNDMtNzZiMTk0ZTg1NTA5Il0sInhtc19jYWUiOiIxIiwieG1zX3RjZHQiOjE1OTQ5MTg2MzF9.0-p5FaqFZQJ3UmB6Hg6UwQEGFm6-3p_bFRTt5OaBtJTqZjYefUjOpUyPAIXMVaPm-f8euCgx1JMv4zgwp63spcgFG370nUYmzfBWX_dCSaoWI2fCdRbxW3Z9qEEEo1sJIQ08HR7WORdWQcreWuOdZmGoRhwU_P78SdTW90-hnqIRQvggGN7_WGcN1_HxIcyrsa09v5pIXrad_noJsmCiwUvRmXBq2PFi5IbHs2vn5qbOEE_9d2xpK_cO48YtuctTmYPe5D1ATEzIR3ENNaNpH5EimvhOsCWHdmGsZ4DBZHoGBStQZBiAl_YmJ5vD9F-e_gcIGnw083Qy5xkdAfC3vw"
    url = "https://management.azure.com/subscriptions/0e51cc83-16a9-4ea1-b6f9-ba23ddfcc8bf/providers/Microsoft.Compute/skus?api-version=2021-07-01&$filter=location eq 'eastus'"
    headers = {
        "Authorization": "Bearer " + token
    }
    max_nic = {}
    next_page_link = url
    while next_page_link != None:
        response = requests.get(next_page_link, headers=headers)
        data = response.json()
        for item in data['value']:
            if "capabilities" in item.keys():
                capabilities = item['capabilities']
                for c_item in capabilities:
                    if c_item['name'] == 'MaxNetworkInterfaces':
                        max_nic[item['name']] = c_item['value']
        next_page_link = None
    #write to csv
    df = pd.DataFrame(max_nic.items(), columns=['InstanceType', 'MaximumNetworkInterfaces'])
    df.to_csv('azure_vm_sizes.csv')


def update_azure_prices(update_nic=False):
    if update_nic:
        update_azure_vm_sizes()
    nic_info = pd.read_csv('azure_vm_sizes.csv')
    next_page_link = "https://prices.azure.com/api/retail/prices?$skip=0&$filter=serviceName%20eq%20%27Virtual%20Machines%27%20and%20priceType%20eq%20%27Consumption%27%20and%20armRegionName%20eq%20%27eastus%27"
    spot_prices: List[Dict[str, str]] = []
    while next_page_link != None:
        with urllib.request.urlopen(next_page_link) as url:
            data = json.loads(url.read().decode())
            for item in data['Items']:
                if 'Spot' in item['skuName']:
                    instance_type_name = item['skuName'].split('Spot')[0].strip()
                    if instance_type_name in nic_info['InstanceType'].values:
                        nic = nic_info.loc[nic_info['InstanceType'] == instance_type_name]['MaximumNetworkInterfaces'].values[0]
                        spot_prices.append({
                            'AvailabilityZone': item['location'],
                            'InstanceType': item['skuName'],
                            'MaximumNetworkInterfaces': nic,
                            'SpotPrice': item['retailPrice'],
                            'PricePerInterface': item['retailPrice'] / nic + nic * 0.005,
                            'Timestamp': item['effectiveStartDate']  
                        })
                    else:
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

def merge_spot_prices():
    aws_spot_prices = pd.read_csv('spot_prices.csv')
    azure_spot_prices = pd.read_csv('azure_spot_prices.csv')
    aws_spot_prices['Provider'] = 'AWS'
    azure_spot_prices['Provider'] = 'Azure'
    spot_prices = pd.concat([aws_spot_prices, azure_spot_prices])
    spot_prices['Timestamp'] = pd.to_datetime(spot_prices['Timestamp'])
    spot_prices = spot_prices.sort_values(by=['Timestamp'])
    spot_prices.to_csv('total_spot_prices.csv')
    return spot_prices

def get_spot_prices():
    df = pd.read_csv('spot_prices.csv')
    return df

def get_all_instances():
    response = ec2.describe_instances()
    # response['Reservations'][0]['Instances'][0]['InstanceId']
    # print(response)
    instance_ids = [instance['InstanceId'] for instance in response['Reservations'][0]['Instances']]
    return instance_ids

def get_all_instances_init_details():
    response = ec2.describe_instances()
    # response['Reservations'][0]['Instances'][0]['InstanceId']
    instances_details = defaultdict(dict)
    for instance in response['Reservations'][0]['Instances']:
        if instance['InstanceId'] != INSTANCE_MANAGER_INSTANCE_ID: # no need to include instance manager since we will not assign clients to it anyway..
            instances_details[instance['InstanceId']] = {"PublicIpAddress": instance['PublicIpAddress']}
    # instance_ids = [instance['InstanceId'] for instance in response['Reservations'][0]['Instances']]
    return instances_details

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

def create_fleet_archive(instance_type, region, launch_template, num):
    # feel free to delete this in the future
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
 
def use_jinyu_launch_templates(instance_type):
    instance_info = get_instance_type([instance_type])
    arch = instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures'][0]
    #x86: lt-04d9c8ac5d00a2078
    #arm: lt-0abc44b6c12879596
    if arch == 'arm64':
        launch_template = 'lt-0abc44b6c12879596'
    else:
        launch_template = 'lt-04d9c8ac5d00a2078'
    return launch_template

class RequestHandler(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('/')[1:]
        print(path)
        match path[0]:
            case 'getNum':
                instances = get_all_instances()
                num = len(instances)
                self._set_response()
                self.wfile.write(str(num).encode('utf-8'))
            case "getInitDetails":
                instances_details = get_all_instances_init_details()
                self._set_response()
                self.wfile.write(str(instances_details).encode('utf-8'))

def run():
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, RequestHandler)
    print('Starting server...')
    httpd.serve_forever()

# example usage of creating 2 instances in us-east-1 with UM account: python3 api.py UM us-east-1a 2
if __name__ == '__main__':
    account_type = sys.argv[1]
    region = sys.argv[2][:-1]
    num = int(sys.argv[3])
    prices = update_spot_prices()
    prices.sort_values(by=['SpotPrice'])
    instance_type = prices.iloc[0]['InstanceType']
    availability_zone = prices.iloc[0]['AvailabilityZone']
    availability_zone = sys.argv[2] # not doing cheapest allocation yet, since we are overriding this with a user provided az (e.g., us-east-1a) instead
    if account_type == 'UM':
        ec2, ce = choose_session(is_UM_AWS=True, region=region)
        launch_template_wireguard = "lt-077e7f82c173dd30a" # not working yet
        launch_template_baseline_working = "lt-07c37429821503fca"
        launch_template = launch_template_wireguard 
    else: # Basically, Jinyu account for now:
        ec2, ce = choose_session(is_UM_AWS=False, region=region)
        instances = get_all_instances()
        #clean up existing instances. (This is dangerous for UM, because our instance-manager or controllers will be deleted too!)
        for instance in instances:
            if instance != "INSTANCE_MANAGER_INSTANCE_ID": # do not delete our UM instance-manager/controller
                response = terminate_instances([instance])
        launch_template = use_jinyu_launch_templates(instance_type)
    
    response = create_fleet(instance_type, availability_zone, launch_template, num)
    print(response)
    run()

    # Some example usage from Patrick:
    """
    response = get_all_instances()

    # Create two instances: 
    UM_launch_template_id = "lt-07c37429821503fca"
    response = create_fleet("t2.micro", "us-east-1c", UM_launch_template_id, 2) # verified working (USE THIS)

    response = create_fleet2("t2.micro", "us-east-1c", UM_launch_template_id, 2) # not working yet

    print(response)

    # Delete instances using the fleet-id key returned from the response above:

    instance_ids = get_specific_instances_with_fleet_id_tag('fleet-4da19c85-1000-4883-a480-c0b7a34b444b')
    print(instance_ids)
    for i in instance_ids:
        response = terminate_instances([i])
        print(response)
    """