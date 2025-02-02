from unittest import mock
from urllib.parse import parse_qs

import orjson
import responses

from sentry.constants import ObjectStatus
from sentry.integrations.slack import SlackNotifyServiceAction
from sentry.integrations.slack.utils import SLACK_RATE_LIMITED_MESSAGE
from sentry.integrations.types import ExternalProviders
from sentry.notifications.additional_attachment_manager import manager
from sentry.silo.base import SiloMode
from sentry.testutils.cases import RuleTestCase
from sentry.testutils.silo import assume_test_silo_mode
from sentry.testutils.skips import requires_snuba
from tests.sentry.integrations.slack.test_notifications import (
    additional_attachment_generator_block_kit,
)

pytestmark = [requires_snuba]


class SlackNotifyActionTest(RuleTestCase):
    rule_cls = SlackNotifyServiceAction

    def setUp(self):
        self.organization = self.get_event().project.organization
        self.integration, self.org_integration = self.create_provider_integration_for(
            organization=self.organization,
            user=self.user,
            external_id="TXXXXXXX1",
            metadata={
                "access_token": "xoxb-xxxxxxxxx-xxxxxxxxxx-xxxxxxxxxxxx",
                "domain_name": "sentry.slack.com",
                "installation_type": "born_as_bot",
            },
            name="Awesome Team",
            provider="slack",
        )

    def assert_form_valid(self, form, expected_channel_id, expected_channel):
        assert form.is_valid()
        assert form.cleaned_data["channel_id"] == expected_channel_id
        assert form.cleaned_data["channel"] == expected_channel

    @responses.activate
    def test_no_upgrade_notice_bot_app(self):
        event = self.get_event()

        rule = self.get_rule(data={"workspace": self.integration.id, "channel": "#my-channel"})

        results = list(rule.after(event=event))
        assert len(results) == 1

        responses.add(
            method=responses.POST,
            url="https://slack.com/api/chat.postMessage",
            body='{"ok": true}',
            status=200,
            content_type="application/json",
        )

        # Trigger rule callback
        results[0].callback(event, futures=[])
        data = parse_qs(responses.calls[0].request.body)

        assert "blocks" in data
        blocks = orjson.loads(data["blocks"][0])

        assert event.title in blocks[0]["text"]["text"]

    def test_render_label_with_notes(self):
        rule = self.get_rule(
            data={
                "workspace": self.integration.id,
                "channel": "#my-channel",
                "channel_id": "",
                "tags": "one, two",
                "notes": "fix this @colleen",
            }
        )

        assert (
            rule.render_label()
            == 'Send a notification to the Awesome Team Slack workspace to #my-channel and show tags [one, two] and notes "fix this @colleen" in notification'
        )

    def test_render_label_without_integration(self):
        with assume_test_silo_mode(SiloMode.CONTROL):
            self.integration.delete()

        rule = self.get_rule(
            data={
                "workspace": self.integration.id,
                "channel": "#my-channel",
                "channel_id": "",
                "tags": "",
            }
        )

        label = rule.render_label()
        assert label == "Send a notification to the [removed] Slack workspace to #my-channel"

    @responses.activate
    def test_valid_bot_channel_selected(self):
        integration, _ = self.create_provider_integration_for(
            organization=self.event.project.organization,
            user=self.user,
            provider="slack",
            name="Awesome Team",
            external_id="TXXXXXXX2",
            metadata={
                "access_token": "xoxp-xxxxxxxxx-xxxxxxxxxx-xxxxxxxxxxxx",
                "domain_name": "sentry.slack.com",
                "installation_type": "born_as_bot",
            },
        )
        rule = self.get_rule(
            data={"workspace": integration.id, "channel": "#my-channel", "tags": ""}
        )

        responses.add(
            method=responses.POST,
            url="https://slack.com/api/chat.scheduleMessage",
            status=200,
            content_type="application/json",
            body=orjson.dumps(
                {"ok": "true", "channel": "chan-id", "scheduled_message_id": "Q1298393284"}
            ),
        )
        responses.add(
            method=responses.POST,
            url="https://slack.com/api/chat.deleteScheduledMessage",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": True}),
        )

        form = rule.get_form_instance()
        assert form.is_valid()
        self.assert_form_valid(form, "chan-id", "#my-channel")

    @responses.activate
    def test_valid_member_selected(self):
        rule = self.get_rule(
            data={"workspace": self.integration.id, "channel": "@morty", "tags": ""}
        )

        responses.add(
            method=responses.POST,
            url="https://slack.com/api/chat.scheduleMessage",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": False, "error": "channel_not_found"}),
        )

        members = {
            "ok": "true",
            "members": [
                {"name": "morty", "id": "morty-id"},
                {"name": "other-user", "id": "user-id"},
            ],
        }

        responses.add(
            method=responses.GET,
            url="https://slack.com/api/users.list",
            status=200,
            content_type="application/json",
            body=orjson.dumps(members),
        )

        form = rule.get_form_instance()
        self.assert_form_valid(form, "morty-id", "@morty")

    @responses.activate
    def test_invalid_channel_selected(self):
        rule = self.get_rule(
            data={"workspace": self.integration.id, "channel": "#my-channel", "tags": ""}
        )

        responses.add(
            method=responses.POST,
            url="https://slack.com/api/chat.scheduleMessage",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": False, "error": "channel_not_found"}),
        )

        members = {"ok": "true", "members": [{"name": "other-member", "id": "member-id"}]}

        responses.add(
            method=responses.GET,
            url="https://slack.com/api/users.list",
            status=200,
            content_type="application/json",
            body=orjson.dumps(members),
        )

        form = rule.get_form_instance()

        assert not form.is_valid()
        assert len(form.errors) == 1

    @responses.activate
    def test_rate_limited_response(self):
        """Should surface a 429 from Slack to the frontend form"""
        responses.add(
            method=responses.POST,
            url="https://slack.com/api/chat.scheduleMessage",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": False, "error": "channel_not_found"}),
        )

        responses.add(
            method=responses.GET,
            url="https://slack.com/api/users.list",
            status=429,
            content_type="application/json",
            body=orjson.dumps({"ok": False, "error": "ratelimited"}),
        )
        rule = self.get_rule(
            data={
                "workspace": self.integration.id,
                "channel": "#my-channel",
                "input_channel_id": "",
                "tags": "",
            }
        )

        form = rule.get_form_instance()
        assert not form.is_valid()
        assert SLACK_RATE_LIMITED_MESSAGE in str(form.errors.values())

    @responses.activate
    def test_channel_id_provided(self):
        responses.add(
            method=responses.GET,
            url="https://slack.com/api/conversations.info",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": "true", "channel": {"name": "my-channel", "id": "C2349874"}}),
        )
        rule = self.get_rule(
            data={
                "workspace": self.integration.id,
                "channel": "#my-channel",
                "input_channel_id": "C2349874",
                "tags": "",
            }
        )

        form = rule.get_form_instance()
        assert form.is_valid()

    @responses.activate
    def test_invalid_channel_id_provided(self):
        responses.add(
            method=responses.GET,
            url="https://slack.com/api/conversations.info",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": False, "error": "channel_not_found"}),
        )
        rule = self.get_rule(
            data={
                "workspace": self.integration.id,
                "channel": "#my-chanel",
                "input_channel_id": "C1234567",
                "tags": "",
            }
        )

        form = rule.get_form_instance()
        assert not form.is_valid()
        assert "Channel not found. Invalid ID provided." in str(form.errors.values())

    @responses.activate
    def test_invalid_channel_name_provided(self):
        responses.add(
            method=responses.GET,
            url="https://slack.com/api/conversations.info",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": "true", "channel": {"name": "my-channel", "id": "C2349874"}}),
        )
        rule = self.get_rule(
            data={
                "workspace": self.integration.id,
                "channel": "#my-chanel",
                "input_channel_id": "C1234567",
                "tags": "",
            }
        )

        form = rule.get_form_instance()
        assert not form.is_valid()
        assert (
            "Received channel name my-channel does not match inputted channel name my-chanel."
            in str(form.errors.values())
        )

    def test_invalid_workspace(self):
        # the workspace _should_ be the integration id

        rule = self.get_rule(data={"workspace": "unknown", "channel": "#my-channel", "tags": ""})

        form = rule.get_form_instance()
        assert not form.is_valid()
        assert ["Slack: Workspace is a required field."] in form.errors.values()

    @responses.activate
    def test_display_name_conflict(self):
        rule = self.get_rule(
            data={"workspace": self.integration.id, "channel": "@morty", "tags": ""}
        )

        responses.add(
            method=responses.POST,
            url="https://slack.com/api/chat.scheduleMessage",
            status=200,
            content_type="application/json",
            body=orjson.dumps({"ok": False, "error": "channel_not_found"}),
        )

        members = {
            "ok": "true",
            "members": [
                {"name": "first-morty", "id": "morty-id", "profile": {"display_name": "morty"}},
                {"name": "second-morty", "id": "user-id", "profile": {"display_name": "morty"}},
            ],
        }

        responses.add(
            method=responses.GET,
            url="https://slack.com/api/users.list",
            status=200,
            content_type="application/json",
            body=orjson.dumps(members),
        )

        form = rule.get_form_instance()
        assert not form.is_valid()
        assert [
            "Slack: Multiple users were found with display name '@morty'. Please use your username, found at sentry.slack.com/account/settings#username."
        ] in form.errors.values()

    def test_disabled_org_integration(self):
        org = self.create_organization(owner=self.user)
        self.create_organization_integration(
            organization_id=org.id, integration=self.integration, status=ObjectStatus.DISABLED
        )
        with assume_test_silo_mode(SiloMode.CONTROL):
            self.org_integration.update(status=ObjectStatus.DISABLED)
        event = self.get_event()

        rule = self.get_rule(data={"workspace": self.integration.id, "channel": "#my-channel"})

        results = list(rule.after(event=event))
        assert len(results) == 0

    @responses.activate
    @mock.patch("sentry.analytics.record")
    def test_additional_attachment(self, mock_record):
        with mock.patch.dict(
            manager.attachment_generators,
            {ExternalProviders.SLACK: additional_attachment_generator_block_kit},
        ):
            event = self.get_event()

            rule = self.get_rule(
                data={
                    "workspace": self.integration.id,
                    "channel": "#my-channel",
                    "channel_id": "123",
                }
            )

            notification_uuid = "123e4567-e89b-12d3-a456-426614174000"
            results = list(rule.after(event=event, notification_uuid=notification_uuid))
            assert len(results) == 1

            responses.add(
                method=responses.POST,
                url="https://slack.com/api/chat.postMessage",
                body='{"ok": true}',
                status=200,
                content_type="application/json",
            )

            # Trigger rule callback
            results[0].callback(event, futures=[])
            data = parse_qs(responses.calls[0].request.body)

            assert "blocks" in data
            blocks = orjson.loads(data["blocks"][0])

            assert event.title in blocks[0]["text"]["text"]
            assert blocks[-2]["text"]["text"] == self.organization.slug
            assert blocks[-1]["text"]["text"] == self.integration.id
            mock_record.assert_called_with(
                "alert.sent",
                provider="slack",
                alert_id="",
                alert_type="issue_alert",
                organization_id=self.organization.id,
                project_id=event.project_id,
                external_id="123",
                notification_uuid=notification_uuid,
            )
            mock_record.assert_any_call(
                "integrations.slack.notification_sent",
                category="issue_alert",
                organization_id=self.organization.id,
                project_id=event.project_id,
                group_id=event.group_id,
                notification_uuid=notification_uuid,
                alert_id=None,
            )

    @responses.activate
    def test_multiple_integrations(self):
        org = self.create_organization(owner=self.user)
        self.create_organization_integration(organization_id=org.id, integration=self.integration)

        event = self.get_event()

        rule = self.get_rule(data={"workspace": self.integration.id, "channel": "#my-channel"})

        results = list(rule.after(event=event))
        assert len(results) == 1
