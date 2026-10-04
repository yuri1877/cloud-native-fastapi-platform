"""Shared moto-backed SQS queue fixture helpers. Not a test file itself."""

import boto3

REGION = "eu-west-2"


def create_test_queue(name: str = "test-queue") -> str:
    """Call inside an active @mock_aws context/decorator. Returns the queue URL."""
    client = boto3.client("sqs", region_name=REGION)
    return client.create_queue(QueueName=name)["QueueUrl"]


def receive_all(queue_url: str) -> list[dict]:
    client = boto3.client("sqs", region_name=REGION)
    response = client.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=10, MessageAttributeNames=["All"]
    )
    return response.get("Messages", [])
