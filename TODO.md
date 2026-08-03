# TODO - Temporary Unavailability (Donor Availability)


## Step 1: Backend groundwork
- [ ] Add donor availability helpers/constants (AVAILABLE / TEMPORARILY_UNAVAILABLE / MANUALLY_DISABLED)
- [ ] Add status inference shim for legacy `is_disabled`
- [x] Update donor query/filtering to use `status == AVAILABLE`


## Step 2: Routes & tokenized enable
- [ ] Implement `POST /disable_profile` flow (duration selection incl. custom date + manual)

- [ ] Implement `POST /extend_unavailability`
- [ ] Implement `POST /enable_profile_now`
- [ ] Implement token issuance + `GET /enable-profile?token=...` validation and enabling

## Step 3: Reminder scheduler
- [ ] Create `reminder_job.py`
- [ ] Daily job: TEMPORARILY_UNAVAILABLE whose `disabledUntil <= today` → send reminder email (no auto-enable)
- [ ] Manual disabled reminders: MANUALLY_DISABLED every 30 days (respect `lastReminderSent`)

## Step 4: Email updates
- [ ] Ensure blood request notifications send only to AVAILABLE donors
- [ ] Implement reminder email template with secure Enable link

## Step 5: UI updates
- [ ] Replace profile Enable/Disable with Temporary Unavailability card + badge + extend button
- [ ] Add duration modal UI in `templates/profile.html`

## Step 6: Tests
- [ ] Add tests for status transitions + reminder recipient filtering
- [ ] Add tests for token validation/expiration

## Step 7: Verification
- [ ] Run tests
- [ ] Manual end-to-end sanity checks (disable, extend, enable, search filtering)

