"""
    Requirements:
        - Given our input (number of proxies, and filter), output the instance combinations required to satisfy this number of proxies.  
        - Other parameters:
            - Rejuvenation period
            - Experiment duration
        - A single experiment will be performed for all 3 bars (optimal, live IP and instance) simultaneously: for equal cost instance reasons
        - After applying the filter:
            - Live IP will choose the cheapest instance according to multi-NIC cost row
            - Instance will choose the cheapest instance according to single-NIC cost row (normal row)
        - Creating the instances: 
            - Live IP instances will be tagged with name "liveip-expX-instanceY" where Y is the number ID
            - Instance rejuvenation instances will be tagged with name "instance-expX-instanceY" where Y is the number ID
            - Optimal instances will be tagged with name "optimal-expX-instanceY" where Y is the number ID
        - Rejuvenation algorithm (i.e., replacing the instances)
            - Live IP: 
        - Helper functions in api.py:
            - be able to retrieve existing instances and change their name
        - Functionalities required by AWS:
            - Cost explorer should be able to retrieve tag values that no longer exist currently (e.g., instances that have been removed..)
"""

if __name__ == '__main__':
    REJUVENATION_PERIOD = sys.argv[1]
    EXPERIMENT_DURATION = sys.argv[2]
    PROXY_COUNT = sys.argv[3] # aka fleet size 
    MIN_VCPU = sys.argv[4]
    MAX_VCPU = sys.argv[5]

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
            if instance != INSTANCE_MANAGER_INSTANCE_ID: # do not delete our UM instance-manager/controller
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