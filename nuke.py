import api, json
initial_ec2, initial_ce = api.choose_session(is_UM_AWS=True, region='us-east-1')
# Excluded instances:
excluded_instances = api.get_excluded_terminate_instances()
api.nuke_all_instances(initial_ec2, excluded_instances)
print("NUKED EVERYTING")