import unittest
from aws_cdk import App, assertions
from iam_cdk_app.iam_cdk_app_stack import IamRoleConfigStack

class TestIamRoleConfigStack(unittest.TestCase):

    def setUp(self):
        self.app = App()

    def test_iam_role_creation_with_trust_policy(self):
        resources = {
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
        stack = IamRoleConfigStack(self.app, "TestStack", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Assert the IAM Role is created with the correct trust policy and managed policy
        template.resource_count_is("AWS::IAM::Role", 1)
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "TestRole",
            "ManagedPolicyArns": ["arn:aws:iam::aws:policy/AmazonEC2FullAccess"],
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }
        })

    def test_inline_policy_creation(self):
        resources = {
            "roles": [
                {
                    "roleName": "TestRoleWithInlinePolicy",
                    "inlinePolicies": {
                        "s3ReadOnlyPolicy": {
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
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithInlinePolicy", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Validate that the IAM Role has the inline policy attached
        template.has_resource_properties("AWS::IAM::Role", {
            "Policies": assertions.Match.array_with([{
                "PolicyName": "s3ReadOnlyPolicy",
                "PolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Action": "s3:ListBucket",
                        "Resource": "*"
                    }]
                }
            }])
        })

    def test_iam_role_with_session_duration_and_permissions_boundary(self):
        resources = {
            "roles": [
                {
                    "roleName": "TestRoleWithSession",
                    "sessionDuration": 7200,
                    "permissionsBoundary": "arn:aws:iam::aws:policy/AdministratorAccess"
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithSession", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Assert that the role has the correct session duration and permissions boundary
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "TestRoleWithSession",
            "MaxSessionDuration": 7200,
            "PermissionsBoundary": "arn:aws:iam::aws:policy/AdministratorAccess"
        })

    def test_iam_role_with_tags(self):
        resources = {
            "roles": [
                {
                    "roleName": "TestRoleWithTags",
                    "tags": [
                        {"key": "Environment", "value": "Production"}
                    ]
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithTags", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Assert that the role has the correct tags
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "TestRoleWithTags",
            "Tags": [
                {"Key": "Environment", "Value": "Production"}
            ]
        })

    def test_iam_role_with_deletion_policy_retain(self):
        resources = {
            "roles": [
                {
                    "roleName": "TestRoleWithRetain",
                    "deletionPolicy": "RETAIN"
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithRetain", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Find the IAM Role resource
        role_resources = template.find_resources("AWS::IAM::Role")
        
        # Check that at least one role has the expected roleName
        role_found = False
        for role_logical_id, role in role_resources.items():
            if role['Properties']['RoleName'] == "TestRoleWithRetain":
                role_found = True
                # Assert that the DeletionPolicy is set to RETAIN
                self.assertEqual(role.get('DeletionPolicy'), 'Retain')
        
        self.assertTrue(role_found, "The IAM role 'TestRoleWithRetain' was not found.")


    def test_invalid_inline_policy(self):
        resources = {
            "roles": [
                {
                    "roleName": "TestRoleWithInvalidInlinePolicy",
                    "inlinePolicies": [
                        {"policyName": "InvalidPolicy", "policyDocument": None}  # Invalid document
                    ]
                }
            ]
        }
        stack = IamRoleConfigStack(self.app, "TestStackWithInvalidPolicy", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Assert that no inline policies are attached
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "TestRoleWithInvalidInlinePolicy",
            "Policies": assertions.Match.absent()
        })

    def test_iam_role_with_trust_policy_conditions(self):
        resources = {
            "roles": [
                {
                    "roleName": "TestRoleWithCondition",
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
        stack = IamRoleConfigStack(self.app, "TestStackWithCondition", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Assert that the trust policy includes the condition sts:ExternalId
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "TestRoleWithCondition",
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
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
    def test_managed_policy_creation(self):
        resources = {
            "roles": [],  # Empty roles for this test case
            "iam_policies": [  # Corrected key to match the stack's implementation
                {
                    "policyName": "TestManagedPolicy",
                    "policyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["s3:ListBucket"],
                                "Resource": ["arn:aws:s3:::example-bucket"]
                            }
                        ]
                    }
                }
            ]
        }

        stack = IamRoleConfigStack(self.app, "TestStack", file_path=None, resources=resources, account_id="123456789012")
        template = assertions.Template.from_stack(stack)

        # Debug: print the synthesized template to inspect the actual output
        print(template.to_json())

        # Verify that a managed policy is created with the expected properties
        template.resource_count_is("AWS::IAM::ManagedPolicy", 1)
        template.has_resource_properties("AWS::IAM::ManagedPolicy", {
            "ManagedPolicyName": "TestManagedPolicy",
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:ListBucket"],
                        "Resource": ["arn:aws:s3:::example-bucket"]
                    }
                ]
            }
        })




if __name__ == '__main__':
    unittest.main()
