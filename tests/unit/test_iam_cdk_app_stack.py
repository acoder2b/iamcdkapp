import unittest
from aws_cdk import App, assertions
from iam_cdk_app.iam_cdk_app_stack import IamRoleConfigStack


class TestIamRoleConfigStack(unittest.TestCase):

    def setUp(self):
        self.app = App()

    def test_iam_role_creation(self):
        config_data = {
            "roles": [
                {
                    "roleName": "TestRole",
                    "trustPolicy": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "ec2.amazonaws.com"},
                                "Action": "sts:AssumeRole"
                            }
                        ]
                    },
                    "managedPolicies": ["arn:aws:iam::aws:policy/AmazonEC2FullAccess"]
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStack", file_path=None, roles=config_data.roles, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Validate that the IAM Role has been created with the correct name and policies
        template.resource_count_is("AWS::IAM::Role", 1)
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "TestRole",
            "ManagedPolicyArns": ["arn:aws:iam::aws:policy/AmazonEC2FullAccess"]
        })

    def test_inline_policy_creation(self):
        config_data = {
            "roles": [
                {
                    "roleName": "TestRoleWithInlinePolicy",
                    "inlinePolicies": [
                        {
                            "policyName": "InlinePolicy",
                            "policyDocument": {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": "s3:ListBucket",
                                        "Resource": "*"
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithInlinePolicy", file_path=None, roles=config_data.roles, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Validate that the IAM Role has the inline policy attached
        template.has_resource_properties("AWS::IAM::Role", {
            "Policies": [{
                "PolicyName": "InlinePolicy",
                "PolicyDocument": {
                    "Statement": [{
                        "Effect": "Allow",
                        "Action": "s3:ListBucket",
                        "Resource": "*"
                    }]
                }
            }]
        })

    def test_iam_role_with_conditions(self):
        config_data = {
            "roles": [
                {
                    "roleName": "TestRoleWithConditions",
                    "trustPolicy": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "lambda.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                                "Condition": {
                                    "StringEquals": {
                                        "aws:PrincipalTag/Environment": "Production"
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithConditions", file_path=None, roles=config_data.roles, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Validate that the IAM Role has the condition in the trust policy
        template.has_resource_properties("AWS::IAM::Role", {
            "AssumeRolePolicyDocument": {
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                    "Condition": {
                        "StringEquals": {
                            "aws:PrincipalTag/Environment": "Production"
                        }
                    }
                }]
            }
        })

    def test_iam_role_with_external_id_condition(self):
        config_data = {
            "roles": [
                {
                    "roleName": "TestRoleWithExternalId",
                    "trustPolicy": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"AWS": "arn:aws:iam::111122223333:root"},
                                "Action": "sts:AssumeRole",
                                "Condition": {
                                    "StringEquals": {
                                        "sts:ExternalId": "12345"
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithExternalId", file_path=None, roles=config_data.roles, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Validate that the IAM Role has the External ID condition in the trust policy
        template.has_resource_properties("AWS::IAM::Role", {
            "AssumeRolePolicyDocument": {
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"AWS": "arn:aws:iam::111122223333:root"},
                    "Action": "sts:AssumeRole",
                    "Condition": {
                        "StringEquals": {
                            "sts:ExternalId": "12345"
                        }
                    }
                }]
            }
        })


if __name__ == '__main__':
    unittest.main()
