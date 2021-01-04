import json


class Settings:
    """Class for managing all settings.
    Automatically saves to the json when a setting is updated

    If new settings are added they must be added as attributes below,
    otherwise KeyError is raised for having too many keys
    """
    def __init__(self):
        # If we're just loading the settings inside init
        self.init = True

        with open('settings.json', 'r') as f:
            settings = json.load(f)

        self.ticket_message = settings.pop('ticket_message', 0)
        self.ticket_category = settings.pop('ticket_category')
        self.ticket_status_channel = settings.pop('ticket_status_channel')

        self.log_channel = settings.pop('log_channel')

        self.report_message = settings.pop('report_message', 0)
        self.report_category = settings.pop('report_category')
        self.report_status_channel = settings.pop('report_status_channel')

        self.suggestions_channel = settings.pop('suggestions_channel')
        self.beta_channel = settings.pop('beta_channel')
        self.help_channel = settings.pop('help_channel')
        self.tournaments_channel = settings.pop('tournaments_channel')
        self.event_channel = settings.pop('event_channel')
        self.automod_channel = settings.pop('automod_channel')

        self.role_channel = settings.pop('role_channel')
        self.pings_message = settings.pop('pings_message', 0)
        self.language_message = settings.pop('language_message', 0)

        self.high5_emoji = settings.pop('high5_emoji')
        self.survivor_emoji = settings.pop('survivor_emoji')
        self.timed_out_role = settings.pop('timed_out_role')
        self.beta_role = settings.pop('beta_role')

        self.update_when_message = settings.pop(
            'update_when_message', 'The update was delayed because you asked for it.'
        )

        # The dict should now be empty, if it's not then that
        # means that there are more keys in the settings json than
        # we have defined here. We throw an error to help, to remind
        # that we must define it above.
        if settings:  # Empty dictionaries evaluate to False
            raise RuntimeError(f'Too many keys in settings.json file: {settings}')

        # Remove it so that it's not saved when changing other attributes
        del self.init

    def __setattr__(self, name, value):
        """Called when an attribute is set or overwritten,
        so we use this to also save the changes to the settings.json
        """
        # Also actually update the attribute
        self.__dict__[name] = value

        try:
            # We don't want to save the settings, as we're currently loading
            if self.init or name == 'init':
                return
        except AttributeError:
            # self.init is not defined, and was removed.
            # We just don't want it to propagate.
            pass

        # Dump all our attributes
        with open('settings.json', 'w') as f:
            json.dump(self.__dict__, f)
