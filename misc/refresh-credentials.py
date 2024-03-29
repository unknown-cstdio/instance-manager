import subprocess, json

proc = subprocess.run(
    'aws sts assume-role --role-arn arn:aws:iam::590184057477:role/spotproxy-pat-umich --role-session-name "SpotProxyPatRoleSession1" --profile "default" '
    '> misc/assume-role-output.json',
    shell=True,
    check=True,
    stdout=subprocess.PIPE)
with open("misc/assume-role-output.json", 'r') as j:
    cred_json = json.loads(j.read())
    # print(cred_json)
    # print(cred_json['Credentials']['AccessKeyId'])
    # print(cred_json['Credentials']['SecretAccessKey'])
    # print(cred_json['Credentials']['SessionToken'])
    with open("/home/ubuntu/.aws/credentials", "r+") as f:
        d = f.readlines()
        f.seek(0)  # skip default credential lines
        for i in d[0:3]:
            f.write(i)
        f.write("[spotproxy-pat-umich-role]\n")
        f.write("aws_access_key_id = " + cred_json['Credentials']['AccessKeyId'] + "\n")
        f.write("aws_secret_access_key = " + cred_json['Credentials']['SecretAccessKey'] + "\n")
        f.write("aws_session_token = " + cred_json['Credentials']['SessionToken'] + "\n")

proc = subprocess.run(
    'aws ec2 describe-instances --region us-east-1 --profile spotproxy-pat-umich-role',
    shell=True,
    check=True,
    stdout=subprocess.PIPE)
print("Testing out that assume role now works:", proc)