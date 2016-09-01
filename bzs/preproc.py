
import mako
import mako.template

from . import const
from . import users

def preprocess_webpage(data, content_user, **additional_arguments):
    if type(data) == bytes:
        data = data.decode('utf-8', 'ignore')
    data = mako.template.Template(
        text=data,
        input_encoding='utf-8',
        output_encoding='utf-8').render(
            placeholder_version_number = const.get_const('version'),
            placeholder_copyright_message = const.get_const('copyright'),
            user_is_administrator = 'Administrators' in content_user.usergroups,
            user_is_standard_user = 'Users' in content_user.usergroups,
            current_user_name = content_user.usr_name,
            current_user_description = content_user.usr_description,
            current_user_followers = len(content_user.followers),
            current_user_friends = len(content_user.friends),
            current_user_usergroups = content_user.usergroups,
            current_user_groups = len(content_user.usergroups),
            **additional_arguments
        )
    return data
