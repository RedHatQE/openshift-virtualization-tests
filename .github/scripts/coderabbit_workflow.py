#!/usr/bin/env python3

# This code was created with the assistance of Claude (Anthropic).*

import os
import re
import sys
from typing import List

from github import Github, GithubException
from github.Issue import Issue
from github.Repository import Repository
from simple_logger.logger import get_logger

LOGGER = get_logger(name="test-plan-flow")


def set_github_output(name: str, value: str) -> None:
    """Set a GitHub Actions output variable."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{name}={value}\n")
        LOGGER.info(f"Set GitHub output: {name}={value}")


LABEL_PLAN_GENERATED = "execution-plan-generated"
LABEL_PLAN_PASSED = "execution-plan-passed"

CODERABBIT_BOT = "coderabbitai[bot]"
RENOVATE_BOT = "renovate"

CODERABBIT_VERIFICATION_PHRASE = "test execution plan verified"
CODERABBIT_PLAN_PHRASE = "test execution plan"


class GitHubClient:
    def __init__(self, token: str, owner: str, repo_name: str, timeout: int = 30) -> None:
        self.gh = Github(login_or_token=token, timeout=timeout)
        self.owner = owner
        self.repo: Repository = self.gh.get_repo(full_name_or_id=f"{owner}/{repo_name}")

    def is_user_in_team(self, username: str, team_slug: str = "cnvqe-bot") -> bool:
        try:
            org = self.gh.get_organization(org=self.owner)
            team = org.get_team_by_slug(slug=team_slug)
            user = self.gh.get_user(login=username)
            return team.has_in_members(member=user)

        except GithubException as ex:
            if ex.status == 404:
                LOGGER.info(f"Team '{team_slug}' not found or user '{username}' not found")
                return False

            LOGGER.error(f"GitHub API error checking team membership: {ex.status} - {ex.data}")
            return False

    def get_issue(self, pr_number: int) -> Issue:
        return self.repo.get_issue(number=pr_number)

    def get_labels(self, pr_number: int) -> List[str]:
        issue = self.get_issue(pr_number=pr_number)
        return [label.name for label in issue.labels]

    def add_label(self, pr_number: int, label: str) -> None:
        issue = self.get_issue(pr_number=pr_number)
        issue.add_to_labels(label)  # noqa: FCN001
        LOGGER.info(f"Added label: {label}")

    def remove_label(self, pr_number: int, label: str) -> bool:
        if not label or not label.strip():
            raise ValueError("Label cannot be empty")
        try:
            issue = self.get_issue(pr_number=pr_number)
            issue.remove_from_labels(label)  # noqa: FCN001
            LOGGER.info(f"Removed label: {label}")
            return True
        except GithubException as e:
            if e.status == 404:
                LOGGER.info(f"Label not present: {label}")
                return False
            LOGGER.error(f"Failed to remove label '{label}' from PR #{pr_number}: {e.status} - {e.data}")
            raise

    def create_comment(self, pr_number: int, body: str) -> None:
        issue = self.get_issue(pr_number=pr_number)
        issue.create_comment(body=body)
        LOGGER.info(f"PR #{pr_number}: Created comment ({len(body)} chars)")


class CodeRabbitWorkflow:
    REQUEST_PLAN_TEMPLATE = """@coderabbitai
<details>
  <summary>Test execution plan request details</summary>

  CRITICAL: You MUST respond with a review comment on the Files Changed tab, NOT as a regular PR comment.
  If it cannot be on the 1st line of the 1st file, add it to any other changed file.

  As an expert software testing engineer, analyze all modified files in this PR
  and create a targeted test execution plan.
  You will create a change request comment on the 1st line of the 1st file in the pr with the test execution plan.
  If you fail to run or post a comment, retry.

  **Analysis Requirements:**

  1. Examine code changes in each modified file
  2. Identify affected code paths, functions, and classes
  3. Analyze pytest-specific elements: fixtures (scope, dependencies), parametrization, markers, conftest changes
  4. Trace test dependencies through imports, shared utilities, and fixture inheritance
  5. Detect new tests introduced in the PR
  6. When a function signature is changed, identify all affected tests (directly or indirectly)
  7. This list is not definite; you MUST ALWAYS check the updated code does not break existing functionality

  **Your deliverable:**
  Your change request comment will be based on the following requirements:

  **Test Execution Plan**

  - `path/to/test_file.py` - When the entire test file needs verification
  - `path/to/test_file.py::TestClass::test_method` - When specific test(s) needed
  - `path/to/test_file.py::test_function` - When specific test(s) needed
  - `-m marker` - When specific marker(s) can be used to cover multiple cases.

  **Guidelines:**

  - Include only tests directly affected by the changes
  - Use a full file path only if ALL tests in that file require verification
  - Use file path + test name if only specific tests are needed
  - If a test marker can cover multiple files/tests, provide the marker
  - Balance coverage vs over-testing - Keep descriptions minimal
  - Do not add a follow-up comment in the PR, only the change request one. THIS IS IMPORTANT! Spams the PR
  - If the user added a comment with `/verified` on the latest commit;
    review the comment to see what was already verified by the user. Address the user verification in your test plan

</details>"""

    REVIEW_REQUEST_TEMPLATE = """@coderabbitai
<details>
  <summary>Test Execution Plan Review Request</summary>

  The PR author has responded to your test execution plan. Please review their response and determine if:

  1. **All comments are adequately addressed** - If the author has provided sufficient information
     or made the requested changes, respond with:
     ```
     Test execution plan verified
     ```
     This will automatically update the PR labels and mark the review as complete.

  2. **More clarification or changes are needed** - If the response is insufficient or
       if you need more specific test instructions, provide:
     - Clear, specific feedback on what's missing
     - Additional test scenarios that need coverage
     - Specific test paths or markers that should be included
     - Any concerns about the proposed test approach

  **Review Guidelines:**
  - Focus on whether the proposed tests adequately cover the code changes
  - Ensure test scope is neither too broad (over-testing) nor too narrow (missing coverage)
  - Verify that critical code paths have appropriate test coverage
  - Check if pytest markers, fixtures, or parametrization changes are properly tested

  **Important:**
  - For verification: Post "Test execution plan verified" as a **regular PR comment** (not on Files Changed)
  - For additional feedback/instructions: Use review comments on the Files Changed tab for line-specific guidance
  - The exact phrase "Test execution plan verified" will trigger automatic label updates
  - Be specific and actionable in your feedback

</details>"""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def _verify_team_membership(self, username: str, command: str, pr_number: int) -> bool:
        is_member = self.client.is_user_in_team(username=username)
        LOGGER.info(f"PR #{pr_number}: User {username} is {'not ' if not is_member else ''}team member")

        if not is_member:
            LOGGER.warning(f"PR #{pr_number}: /{command} is restricted to team members only")

        return is_member

    def handle_new_commit(self, pr_number: int) -> None:
        LOGGER.info(f"PR #{pr_number}: New commit pushed, checking execution plan labels")

        current_labels = self.client.get_labels(pr_number=pr_number)
        removed_labels = []
        for label in [LABEL_PLAN_GENERATED, LABEL_PLAN_PASSED]:
            if label in current_labels:
                self.client.remove_label(pr_number=pr_number, label=label)
                removed_labels.append(label)

        if removed_labels:
            LOGGER.info(f"PR #{pr_number}: Removed labels {removed_labels} - test plan needs to be regenerated")
        else:
            LOGGER.info(f"PR #{pr_number}: No execution plan labels present, nothing to remove")

    def handle_coderabbit_response(self, pr_number: int, comment_body: str) -> None:
        if not comment_body or len(comment_body.strip()) < 10:
            LOGGER.info(f"PR #{pr_number}: CodeRabbit comment is too short, skipping")
            return

        comment_lower = comment_body.lower()

        if CODERABBIT_VERIFICATION_PHRASE in comment_lower:
            LOGGER.info(f"PR #{pr_number}: CodeRabbit posted verification message")
            self.client.remove_label(pr_number=pr_number, label=LABEL_PLAN_GENERATED)
            self.client.add_label(pr_number=pr_number, label=LABEL_PLAN_PASSED)
            LOGGER.info(f"PR #{pr_number}: Labels updated - plan verified successfully")

        elif CODERABBIT_PLAN_PHRASE in comment_lower:
            LOGGER.info(f"PR #{pr_number}: CodeRabbit posted test execution plan")
            self.client.add_label(pr_number=pr_number, label=LABEL_PLAN_GENERATED)
            LOGGER.info(f"PR #{pr_number}: Added {LABEL_PLAN_GENERATED} label")
        else:
            LOGGER.info(f"PR #{pr_number}: CodeRabbit comment does not contain test execution plan keywords, skipping")

    def request_execution_plan(self, pr_number: int, commenter: str, has_generate: bool) -> bool:
        if has_generate:
            LOGGER.info(f"PR #{pr_number}: User requested test execution plan via /generate-execution-plan")
        else:
            LOGGER.info(f"PR #{pr_number}: User triggered plan generation via /verified without existing plan")

        cmd = "generate-execution-plan" if has_generate else "verified"
        if not self._verify_team_membership(username=commenter, command=cmd, pr_number=pr_number):
            LOGGER.info(f"PR #{pr_number}: Authorization denied for /{cmd} command")
            return False

        self.client.create_comment(pr_number=pr_number, body=self.REQUEST_PLAN_TEMPLATE)
        LOGGER.info(f"PR #{pr_number}: Requested test execution plan from CodeRabbit")

        if has_generate:
            set_github_output(name="plan_requested", value="true")

        return has_generate

    def request_plan_review(self, pr_number: int, commenter: str, comment_body: str, has_verified: bool) -> None:
        labels = self.client.get_labels(pr_number=pr_number)
        has_generated = LABEL_PLAN_GENERATED in labels
        has_passed = LABEL_PLAN_PASSED in labels

        LOGGER.info(f"PR #{pr_number}: Labels - generated: {has_generated}, passed: {has_passed}")

        if has_generated and has_passed:
            LOGGER.warning(
                f"PR #{pr_number}: Both labels exist - invalid state, removing execution-plan-passed to reset"
            )
            self.client.remove_label(pr_number=pr_number, label=LABEL_PLAN_PASSED)
            has_passed = False

        if not has_generated:
            LOGGER.info(f"PR #{pr_number}: No execution-plan-generated label, skipping review request")
            return

        comment_lower = comment_body.lower()
        is_relevant = CODERABBIT_PLAN_PHRASE in comment_lower or "@coderabbitai" in comment_lower or has_verified

        if not is_relevant:
            LOGGER.info(f"PR #{pr_number}: Comment is not a response to test plan, skipping")
            return

        if has_verified and not self._verify_team_membership(
            username=commenter, command="verified", pr_number=pr_number
        ):
            LOGGER.info(f"PR #{pr_number}: Authorization denied for /verified command")
            return

        LOGGER.info(f"PR #{pr_number}: User responded to test plan, requesting CodeRabbit review")
        self.client.create_comment(pr_number=pr_number, body=self.REVIEW_REQUEST_TEMPLATE)
        LOGGER.info(f"PR #{pr_number}: Requested CodeRabbit to review user response")


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    event_action = os.environ.get("GITHUB_EVENT_ACTION")
    pr_number_str = os.environ.get("GITHUB_PR_NUMBER", "")
    comment_body = os.environ.get("COMMENT_BODY", "")
    review_body = os.environ.get("REVIEW_BODY", "")
    commenter = os.environ.get("COMMENTER_LOGIN", "")

    if not all([token, repository, event_name]):
        LOGGER.error("Missing required environment variables")
        sys.exit(1)

    try:
        owner, repo = repository.split("/")
    except ValueError:
        LOGGER.error(f"Invalid repository format: {repository}")
        sys.exit(1)

    if pr_number_str:
        try:
            pr_number: int = int(pr_number_str)
        except ValueError:
            LOGGER.error(f"Invalid PR number format: '{pr_number_str}' - must be integer")
            sys.exit(1)
    else:
        LOGGER.error("Missing PR number in environment variables")
        sys.exit(1)

    LOGGER.info(f"Event: {event_name}, Action: {event_action}")

    client = GitHubClient(token=token, owner=owner, repo_name=repo)
    LOGGER.info(f"PR #{pr_number}: Initialized GitHub client for {owner}/{repo}")
    workflow = CodeRabbitWorkflow(client=client)

    if event_name == "pull_request_target" and event_action == "synchronize":
        workflow.handle_new_commit(pr_number=pr_number)
        return

    if event_name in ["issue_comment", "pull_request_review_comment", "pull_request_review"]:
        if not commenter:
            LOGGER.info("No commenter found, skipping")
            return

        LOGGER.info(f"PR #{pr_number}, Commenter: {commenter}")

        if RENOVATE_BOT in commenter.lower():
            LOGGER.info("Renovate comment, skipping")
            return

        body = comment_body or review_body

        if not body:
            LOGGER.info("No comment body found, skipping")
            return

        if commenter == CODERABBIT_BOT:
            workflow.handle_coderabbit_response(pr_number=pr_number, comment_body=body)
            return

        body_lower = body.lower()
        has_generate = re.search(pattern=r"(?:^|\s)/generate-execution-plan(?:\s|$)", string=body_lower) is not None
        has_verified = re.search(pattern=r"(?:^|\s)/verified(?:\s|$)", string=body_lower) is not None

        LOGGER.info(f"Commands - generate: {has_generate}, verified: {has_verified}")

        if has_generate:
            workflow.request_execution_plan(pr_number=pr_number, commenter=commenter, has_generate=True)
            return

        if has_verified:
            labels = workflow.client.get_labels(pr_number=pr_number)
            if LABEL_PLAN_GENERATED not in labels:
                workflow.request_execution_plan(pr_number=pr_number, commenter=commenter, has_generate=False)
                return

        workflow.request_plan_review(
            pr_number=pr_number, commenter=commenter, comment_body=body, has_verified=has_verified
        )
        return

    LOGGER.info("No action taken - event does not match any scenario")


if __name__ == "__main__":
    main()
