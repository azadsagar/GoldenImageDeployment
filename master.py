#!/usr/bin/python
# Golden Image deployment with Autoscaling 
# Written by Sagar Barai, July 2018

import boto3
import sys
import time

if len(sys.argv) != 3:
    print("Usage : " + sys.argv[0] + " [Instance-ID] \"AutoScalingGroupName\"")
    print("Where Instance-ID is AWS golden image instance and")
    print("AutoscalingGroup is where launch configuration should be updated")
    print("Note : If your autoscaling group contains whitespaces, use quotes \"\"")
    exit(1)

session = boto3.Session(profile_name='terraform')
ec2 = session.resource('ec2', region_name='us-east-2')
client = session.client('autoscaling', region_name='us-east-2')


def create_ami_backup(instance_id):

    try:

        print("Identifying instance...")

        instance = ec2.Instance(instance_id)
        hostname = ""
        for t in instance.tags:
            if t["Key"] == "Name":
                print(t["Value"])
                hostname = t["Value"]
                break

        print("Creating Backup...")

        ami_image = instance.create_image(Name=hostname + "_AMI_" + time.strftime("%d-%m-%Y-%H-%M"), NoReboot=True)

        ami_image.create_tags(Tags=[
            {
                "Key": "Name",
                "Value": hostname + "_AMI_" + time.strftime("%d-%m-%Y-%H-%M")
            }
        ])

        ami_image.wait_until_exists(Filters=[{'Name': 'state', 'Values': ['available']}])

        print("AMI Backup complete..." + str(ami_image.state))

        return ami_image

    except Exception as e:
        print(e)
        exit(1)


def create_new_launch_config(asg_name, ami_id):

    try:

        print("Retriving Autoscaling Configuration Details...")

        asgdata = client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if asgdata["ResponseMetadata"]["HTTPStatusCode"] != 200:
            print("Unable to retrive data, response code is " + asgdata["ResponseMetadata"]["HTTPStatusCode"])
            exit(1)

        asgarn = asgdata["AutoScalingGroups"][0]["AutoScalingGroupARN"]
        asg_lc_name = asgdata["AutoScalingGroups"][0]["LaunchConfigurationName"]

        launch_config_data = client.describe_launch_configurations(LaunchConfigurationNames=[asg_lc_name])

        if launch_config_data["ResponseMetadata"]["HTTPStatusCode"] != 200:
            print("Unable to retrive data, response code is " + launch_config_data["ResponseMetadata"]["HTTPStatusCode"])
            exit(1)

        iam_instance_profile = launch_config_data['LaunchConfigurations'][0]["IamInstanceProfile"]
        #launch_config_arn = launch_config_data['LaunchConfigurations'][0]["LaunchConfigurationARN"]
        lc_key_name = launch_config_data['LaunchConfigurations'][0]["KeyName"]
        lc_sec_groups = launch_config_data['LaunchConfigurations'][0]["SecurityGroups"]
        # create a new configuration name
        temp_name = launch_config_data['LaunchConfigurations'][0]["LaunchConfigurationName"]
        temp_name = temp_name[:-16] + time.strftime("%d-%m-%Y-%H-%M")
        lc_config_name = temp_name
        lc_instance_type = launch_config_data['LaunchConfigurations'][0]["InstanceType"]

        print("Creating New Launch configuration from " + launch_config_data['LaunchConfigurations'][0]["LaunchConfigurationName"])

        lc_new_config = client.create_launch_configuration(
            LaunchConfigurationName=lc_config_name,
            ImageId=str(ami_id),
            KeyName=lc_key_name,
            SecurityGroups=lc_sec_groups,
            InstanceMonitoring=launch_config_data['LaunchConfigurations'][0]["InstanceMonitoring"],
            IamInstanceProfile=iam_instance_profile,
            InstanceType=lc_instance_type
        )

        if lc_new_config["ResponseMetadata"]["HTTPStatusCode"] != 200:
            print("Unable to create new launch configuration, return code is " + lc_new_config["ResponseMetadata"]["HTTPStatusCode"])
            exit(1)
        else:
            print("New Launch Config created : " + lc_config_name)

        return lc_config_name, asgdata["AutoScalingGroups"][0]["Instances"][0]["InstanceId"]

    except Exception as e:
        print(e)
        exit(1)


def update_asg_config(asg_name, lc_name, min_size, desired_size):

    try:

        response = client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            LaunchConfigurationName=lc_name,
            MinSize=min_size,
            DesiredCapacity=desired_size
        )

        if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
            print("Unable to update autoscaling group, response code is " + response["ResponseMetadata"]["HTTPStatusCode"])
            exit(1)

    except Exception as e:
        print(e)
        exit(1)


image = create_ami_backup(sys.argv[1])
new_lc, old_instance_id = create_new_launch_config(sys.argv[2], str(image.image_id))
print("Updating Autoscaling group with new Launch config and Min and Desired Instance size to 2...")
update_asg_config(sys.argv[2], new_lc, 2, 2)
print("Waiting for new instance to launch...")
time.sleep(60)
new_asg_data = client.describe_auto_scaling_groups(AutoScalingGroupNames=[sys.argv[2]])

if new_asg_data["ResponseMetadata"]["HTTPStatusCode"] != 200:
    print("Unable to get new instance details, response code is : " + new_asg_data["ResponseMetadata"]["HTTPStatusCode"])
    exit(1)

new_instance_id = ""


if new_asg_data["AutoScalingGroups"][0]["Instances"][0]["InstanceId"] == old_instance_id:
    new_instance_id = new_asg_data["AutoScalingGroups"][0]["Instances"][1]["InstanceId"]
else:
    new_instance_id = new_asg_data["AutoScalingGroups"][0]["Instances"][0]["InstanceId"]

print("New instance Launced : " + new_instance_id)
print("Waiting for instance status check to pass ok")
temp = session.client('ec2', region_name='us-east-2')
waiter = temp.get_waiter('system_status_ok')
waiter1 = temp.get_waiter('instance_status_ok')
waiter.wait(Filters=[{'Name': 'instance-status.status','Values': ['ok']}], InstanceIds=[new_instance_id])
waiter.wait(Filters=[{'Name': 'system-status.status','Values': ['ok']}], InstanceIds=[new_instance_id])
waiter1.wait(Filters=[{'Name': 'instance-status.status','Values': ['ok']}], InstanceIds=[new_instance_id])
waiter1.wait(Filters=[{'Name': 'system-status.status','Values': ['ok']}], InstanceIds=[new_instance_id])

print("Done !")

print("Reconfiguring Minimum and Desired Instance count to 1")
update_asg_config(sys.argv[2], new_lc, 1, 1)

print("Script Execution Completed !")