import logging
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import jinja2
import requests

from .auth import get_access_token
from .settings import RunSettings, InitSettings, TimeZoneCache
from .util import get_adjacent_events, get_datetime

log = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")


class Context:
    """
    Application context for storing stateful information during execution.
    """

    headers: dict | None = None
    mailbox_settings_response: requests.Response | None = None
    mailbox_timezone: ZoneInfo | None = None


def init(settings: InitSettings, ctx: Context = Context()):
    """
    Initialize the application by acquiring and caching an access token.

    Args:
        settings (Settings): Application configuration
        ctx (Context): Execution context
    """
    log.info("Initializing token cache.")
    token_cache = settings.cache.get_token_cache()

    log.info("Getting access token.")
    access_token = get_access_token(settings.app, token_cache)

    log.info("Saving token cache.")
    settings.cache.put_token_cache(token_cache)

    # Prepare API request headers
    ctx.headers = {"Authorization": f"Bearer {access_token}"}

    # Retrieve mailbox settings
    ctx.mailbox_settings_response = requests.get(
        f"{settings.app.base_url}/me/mailboxSettings", headers=ctx.headers
    )
    ctx.mailbox_settings_response.raise_for_status()

    log.debug(f"Mailbox settings: {ctx.mailbox_settings_response.json()}")

    # Determine mailbox timezone
    mailbox_timezone_name = ctx.mailbox_settings_response.json().get("timeZone")
    log.info(f"Mailbox timezone (Windows): {mailbox_timezone_name}")

    timezone_cache = settings.cache.get_tz_cache()
    log.info(f"Timezone cache: {timezone_cache}")

    if not timezone_cache or timezone_cache.windows_tz != mailbox_timezone_name:
        log.info("Updating timezone cache...")

        # Retrieve Windows timezone to IANA timezone mapping.
        windows_zones_response = requests.get(
            "https://raw.githubusercontent.com/unicode-org/cldr/main/common/supplemental/windowsZones.xml"
        )

        # Raise an exception if the request was unsuccessful.
        windows_zones_response.raise_for_status()

        iana_tz = None

        # Parse the XML content.
        root = ElementTree.fromstring(windows_zones_response.text)

        # Find the IANA timezone for the given Windows timezone.
        for mapZone in root.findall(".//mapZone"):
            if mapZone.get("other") == mailbox_timezone_name:
                iana_name = mapZone.get("type").split()[0]
                iana_tz = iana_name

        if not iana_tz:
            raise ValueError(
                f"Failed to find IANA timezone for Windows timezone: {mailbox_timezone_name}"
            )

        # Update timezone cache.
        timezone_cache = TimeZoneCache(
            windows_tz=mailbox_timezone_name, iana_tz=iana_tz
        )
        settings.cache.put_tz_cache(timezone_cache)

    ctx.mailbox_timezone = ZoneInfo(timezone_cache.iana_tz)
    log.info(f"Mailbox timezone (IANA): {ctx.mailbox_timezone}")


def run(settings: RunSettings, ctx: Context = Context()):
    """
    Main execution method for managing absence automatic replies.

    Detects upcoming absence events, configures automatic replies, and updates mailbox settings accordingly.

    Args:
        settings (Settings): Application configuration
        ctx (Context): Execution context
    """
    init(settings, ctx)

    # Initialize Jinja2 environment with custom filters.
    env = jinja2.Environment()
    env.filters["date"] = (
        lambda value: value.strftime(settings.absence.date_format)
        if isinstance(value, datetime)
        else value
    )

    # Determine absence period
    now = datetime.now(UTC).astimezone(UTC)
    start_time = now.isoformat()
    end_time = (now + timedelta(days=settings.absence.future_period_days)).isoformat()

    log.info(
        f"Querying calendar view for upcoming or ongoing absence from {start_time} to {end_time}."
    )

    # Query calendar for next absence event
    calendar_view_response = requests.get(
        f"{settings.app.base_url}/me/calendar/calendarView",
        headers=ctx.headers,
        params={
            "startDateTime": start_time,
            "endDateTime": end_time,
            "$filter": f"subject eq '{settings.absence.keyword}' and isAllDay eq true",
            "$orderby": "start/dateTime",
            "$top": 1,
        },
    )
    calendar_view_response.raise_for_status()

    calendar_events = calendar_view_response.json().get("value", [])
    next_vacation = calendar_events[0] if calendar_events else None

    log.debug(f"Next vacation event: {next_vacation}")

    if not next_vacation:
        log.info("No upcoming vacation events found.")
        return

    # Process vacation event details
    vacation_start = get_datetime(next_vacation["start"]).replace(
        tzinfo=ctx.mailbox_timezone
    )
    vacation_end = get_datetime(next_vacation["end"]).replace(
        tzinfo=ctx.mailbox_timezone
    )

    log.info(
        f"Found upcoming vacation event from {vacation_start.strftime('%Y-%m-%d')} to {vacation_end.strftime('%Y-%m-%d')}."
    )

    # Find adjacent vacation events
    log.info("Finding adjacent/overlapping vacation events...")
    adjacent_events = get_adjacent_events(
        ctx.mailbox_timezone, settings, ctx.headers, next_vacation
    )
    log.info(f"Found {len(adjacent_events)} adjacent/overlapping vacation events.")

    if adjacent_events:
        log.info("Updating vacation period to include adjacent/overlapping events.")
        vacation_end = get_datetime(adjacent_events[-1]["end"]).replace(
            tzinfo=ctx.mailbox_timezone
        )
        log.info(
            f"Updated vacation period to end on {vacation_end.strftime('%Y-%m-%d')}."
        )

    # Get current automatic replies settings.
    auto_reply_settings = ctx.mailbox_settings_response.json().get(
        "automaticRepliesSetting", {}
    )

    log.debug(f"Current automatic replies settings: {auto_reply_settings}")

    # Check if automatic replies are currently active.
    auto_replies_active = auto_reply_settings.get(
        "status"
    )  # == 'scheduled' or auto_reply_settings.get('status') == 'alwaysEnabled'

    scheduled_start_date_time = (
        get_datetime(auto_reply_settings.get("scheduledStartDateTime"))
        if auto_replies_active == "scheduled"
        else None
    )

    scheduled_end_date_time = (
        get_datetime(auto_reply_settings.get("scheduledEndDateTime"))
        if auto_replies_active == "scheduled"
        else None
    )

    log.info(
        f"Current automatic replies status: {auto_replies_active}"
        + (
            f" from {scheduled_start_date_time} to {scheduled_end_date_time}"
            if auto_replies_active == "scheduled"
            else ""
        )
    )

    # Get internal and external absence messages.
    internal_msg_current = auto_reply_settings.get("internalReplyMessage")
    external_msg_current = auto_reply_settings.get("externalReplyMessage")

    log.debug(f"Current internal absence message: {internal_msg_current}")
    log.debug(f"Current external absence message: {external_msg_current}")

    # Initialize internal and external absence messages.
    internal_msg = None
    external_msg = None

    # Check if autotomatic replies should be updated.

    should_update = False

    if auto_replies_active == "disabled":
        # Schedule automatic replies since they're not active.
        should_update = True
        log.info(
            "Automatic replies are not currently active. Scheduling for vacation period."
        )
    elif auto_replies_active == "alwaysEnabled":
        # Do not change automatic replies if they're always enabled.
        should_update = False
        log.info(
            "Automatic replies are always enabled. Not scheduling for vacation period."
        )
    elif auto_replies_active == "scheduled":
        if scheduled_end_date_time < now:
            # Current scheduled period has already ended.
            should_update = True
            log.info(
                "Automatic replies are scheduled but the current period has already ended. Scheduling for vacation period."
            )
        elif (
            vacation_start == scheduled_start_date_time
            and vacation_end == scheduled_end_date_time
        ):
            render_args = {"start": vacation_start, "end": vacation_end}
            internal_msg = env.from_string(
                settings.absence.internal_reply_template.get_template()
            ).render(**render_args)
            external_msg = env.from_string(
                settings.absence.external_reply_template.get_template()
            ).render(**render_args)

            if (
                internal_msg_current != internal_msg
                or external_msg_current != external_msg
            ):
                should_update = True
                log.info(
                    "Automatic replies are already scheduled for the vacation period, but messages are different. Updating messages."
                )
            else:
                should_update = False
                log.info(
                    "Automatic replies are already scheduled for the vacation period with the same messages. Not updating."
                )
        elif scheduled_start_date_time < vacation_start:
            # Current scheduled period starts before vacation period.
            if scheduled_end_date_time < vacation_start:
                # Scheduled period ends before vacation period starts.

                # CHeck if difference between scheduled end and vacation start is less than MAX_DELTA_HOURS
                if (
                    vacation_start - scheduled_end_date_time
                ).total_seconds() / 3600 < settings.absence.max_delta_hours:
                    should_update = True
                    log.info(
                        f"Automatic replies are scheduled but end before vacation period starts. However, the difference is less than {settings.absence.max_delta_hours} hours. Scheduling current and vacation period."
                    )
                    # Determine beginning and end of overlapping period.
                    vacation_start = min(vacation_start, scheduled_start_date_time)
                    vacation_end = max(vacation_end, scheduled_end_date_time)
                else:
                    should_update = False
                    log.info(
                        "Automatic replies are scheduled prior to beginning of vacation period."
                    )
            else:
                # Scheduled period overlaps with vacation period.
                should_update = True
                log.info(
                    "Automatic replies are scheduled but overlap with the vacation period. Scheduling current and vacation period."
                )
                # Determine beginning and end of overlapping period.
                vacation_start = min(vacation_start, scheduled_start_date_time)
                vacation_end = max(vacation_end, scheduled_end_date_time)
        else:
            # Update automatic replies if the vacation period starts before the current scheduled period.
            should_update = True
            log.info(
                "Automatic replies are scheduled but the vacation period starts before the current scheduled period. Scheduling for vacation period."
            )

    if should_update:
        # Ensure internal and external messages are available.
        if internal_msg is None or external_msg is None:
            render_args = {"start": vacation_start, "end": vacation_end}
            internal_msg = env.from_string(
                settings.absence.internal_reply_template.get_template()
            ).render(**render_args)
            external_msg = env.from_string(
                settings.absence.external_reply_template.get_template()
            ).render(**render_args)

        log.info(
            f"Scheduling automatic replies for vacation period from {vacation_start} to {vacation_end}."
        )

        log.debug(f"Internal absence message: {internal_msg}")
        log.debug(f"External absence message: {external_msg}")

        # Prepare the update payload.
        update_payload = {
            "automaticRepliesSetting": {
                "status": "scheduled",
                "scheduledStartDateTime": {
                    "dateTime": vacation_start.astimezone(ctx.mailbox_timezone)
                    .replace(tzinfo=None)
                    .isoformat(),
                    "timeZone": ctx.mailbox_timezone.key,
                },
                "scheduledEndDateTime": {
                    "dateTime": vacation_end.astimezone(ctx.mailbox_timezone)
                    .replace(tzinfo=None)
                    .isoformat(),
                    "timeZone": ctx.mailbox_timezone.key,
                },
                "internalReplyMessage": internal_msg,
                "externalReplyMessage": external_msg,
                # Send reply to all external recipients.
                "externalAudience": "all",
            }
        }

        # Update automatic replies
        if not settings.dry_run:
            update_response = requests.patch(
                f"{settings.app.base_url}/me/mailboxSettings",
                headers=ctx.headers,
                json=update_payload,
            )

            if update_response.status_code == 200:
                log.info("Successfully updated automatic replies for vacation period.")
            else:
                log.error(
                    f"Failed to update automatic replies: {update_response.status_code} {update_response.text}"
                )
        else:
            log.info("Dry run mode enabled. Automatic replies not updated.")

    log.info("Run complete.")
