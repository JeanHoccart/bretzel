"""``/form`` — fields, labels, validation and a submit that runs Python."""

from bretzel import refreshable, ui
from bretzel.state import PageState, field, validator
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A form posts its fields to a Python handler as one typed state; "
           "a validator that raises puts its message under the field.")

TAKEN_WORKSPACES = {"acme", "northwind", "globex"}


class SignupForm(PageState):
    full_name: str = field(default="")
    work_email: str = field(default="")
    workspace: str = field(default="")
    password: str = field(default="")
    confirm: str = field(default="")

    @validator("work_email")
    def check_email(self, value: str) -> str:
        value = (value or "").strip().lower()
        if value and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("Enter a work email like maya@company.com.")
        return value

    @validator("workspace")
    def check_workspace(self, value: str) -> str:
        value = (value or "").strip().lower()
        if value in TAKEN_WORKSPACES:
            raise ValueError(f"{value}.bretzel.app is already taken.")
        return value

    @validator("password")
    def check_password(self, value: str) -> str:
        if value and len(value) < 8:
            raise ValueError("Use at least 8 characters.")
        return value

    @validator("confirm")
    def check_confirm(self, value: str) -> str:
        if value and self.password and value != self.password:
            raise ValueError("The two passwords are different.")
        return value


def create_account(form: SignupForm) -> None:
    if form.errors:
        return
    ui.notification(f"Welcome aboard, {form.full_name}!",
                    title="Workspace created", color="success")
    form.full_name = form.work_email = form.workspace = ""
    form.password = form.confirm = ""


@refreshable
def signup_form() -> None:
    form = SignupForm()
    with (ui.card(padding="lg", classes="w-full max-w-md"),
          ui.form(on_submit=create_account), ui.vstack(gap="md")):
        with ui.vstack(gap="xs"):
            ui.heading("Create your workspace", level=3, size="lg")
            ui.text("Free for 14 days. No card required.", color="muted",
                    size="sm")
        with ui.form_field(label="Full name", required=True):
            ui.input(value=form.full_name, placeholder="Maya Chen",
                     autocomplete="name")
        with ui.form_field(label="Work email", required=True):
            ui.input(value=form.work_email, type="email", icon_left="mail",
                     placeholder="maya@company.com")
        with ui.form_field(label="Workspace URL",
                           hint="Try “acme” to see a taken name."):
            ui.input(value=form.workspace, prefix="https://",
                     suffix=".bretzel.app", placeholder="your-team")
        with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
            with ui.form_field(label="Password", required=True):
                ui.input(value=form.password, type="password")
            with ui.form_field(label="Confirm password", required=True):
                ui.input(value=form.confirm, type="password")
        ui.button("Create workspace", type="submit", icon_right="arrow-right",
                  classes="w-full")


def signup() -> None:
    signup_form()


def field_anatomy() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-sm"):
        with ui.form_field(label="Company name", required=True):
            ui.input(value="Northwind Traders")
        with ui.form_field(label="VAT number",
                           hint="Shown on every invoice you send."):
            ui.input(placeholder="FR 40 303 265 045")
        with ui.form_field(label="Billing email",
                           error="This address bounced last month."):
            ui.input(value="billing@northwind", type="email")


TIMEZONES = [
    ("Europe/Paris", "Paris (GMT+2)"),
    ("Europe/London", "London (GMT+1)"),
    ("America/New_York", "New York (GMT−4)"),
    ("America/Los_Angeles", "San Francisco (GMT−7)"),
    ("Asia/Tokyo", "Tokyo (GMT+9)"),
]


class ProfileSettings(PageState):
    display_name: str = field(default="Maya Chen")
    job_title: str = field(default="Product designer")
    timezone: str = field(default="Europe/Paris")
    bio: str = field(default="Designing calm tools for busy teams.")
    weekly_digest: bool = field(default=True)

    @validator("display_name")
    def check_name(self, value: str) -> str:
        value = (value or "").strip()
        if len(value) < 2:
            raise ValueError("At least two characters, so teammates can "
                             "@mention you.")
        return value


def save_profile(form: ProfileSettings) -> None:
    if form.errors:
        return
    ui.notification("Your profile is up to date.", title="Saved",
                    color="success")


@refreshable
def profile_form() -> None:
    profile = ProfileSettings()
    with ui.form(on_submit=save_profile), ui.vstack(gap="lg"):
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            with ui.form_field(label="Display name", required=True):
                ui.input(value=profile.display_name)
            with ui.form_field(label="Job title"):
                ui.input(value=profile.job_title)
            with ui.form_field(label="Time zone",
                               hint="Reminders go out at 9:00 your time."):
                ui.select(TIMEZONES, value=profile.timezone)
            with ui.form_field(label="Email"):
                ui.switch(checked=profile.weekly_digest,
                          label="Send me the weekly digest")
        with ui.form_field(label="Bio", hint="160 characters at most."):
            ui.textarea(value=profile.bio, rows=3, maxlength=160)
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Cancel", variant="ghost")
            ui.button("Save changes", type="submit", icon_left="check")


def settings() -> None:
    profile_form()


def page() -> None:
    page_header("form", "Form", SUMMARY)
    example("Sign-up with validation", signup,
            uses=[SignupForm, create_account, signup_form],
            note="The handler receives the whole form as SignupForm. Each "
                 "validator that raises shows its message under its own field "
                 "— and clears as soon as you type. Try a short password, or "
                 "two that differ.")
    example("Label, hint, error", field_anatomy,
            note="ui.form_field is the frame around any input: a label (with "
                 "a required mark), a hint, and an error under the input.")
    example("A settings form", settings, full=True,
            uses=[ProfileSettings, save_profile, profile_form],
            note="Inputs, a select, a switch and a textarea bound to one "
                 "state. Shorten the display name to one letter and save.")
