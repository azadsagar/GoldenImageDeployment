#!/usr/bin/python

import boto3
import sys
import time


if len(sys.argv) != 2:
    print("Usage : " + sys.argv[0] + " [Instance-ID]")
    print("Where Instance-ID is AWS golden image instance")
    exit(1)

session = boto3.Session(profile_name='terraform')
ec2 = session.resource('ec2', region_name='us-east-2')


def create_ami_backup(instance_id):

    try:

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


image = create_ami_backup(sys.argv[1])
