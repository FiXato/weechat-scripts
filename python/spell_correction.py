# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 by nils_2 <weechatter@arcor.de>
#
# a simple spell correction for a "mispelled" word
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# 2012-01-11: nils_2, (freenode.#weechat)
#       0.1 : - under dev -
#
# requires: WeeChat version 0.3.x
#
# Development is currently hosted at
# https://github.com/weechatter/weechat-scripts

# TODO: /spell_correction next and /spell_correction previous instead 
# I would also appreciate it if it would list from which dictionary the suggestion came.

try:
    import weechat, re, sys, string

except Exception:
    print("This script must be run under WeeChat.")
    print("Get WeeChat now at: http://www.weechat.org/")
    quit()

SCRIPT_NAME     = "spell_correction"
SCRIPT_AUTHOR   = "nils_2 <weechatter@arcor.de>"
SCRIPT_VERSION  = "0.1"
SCRIPT_LICENSE  = "GPL"
SCRIPT_DESC     = "a simple spell correction for a 'mispelled' word"

OPTIONS         = { 'auto_pop_up_item'       : ('off','automatic pop-up suggestion item on a misspelled word'),
                    'auto_replace'           : ('on','replaces misspelled word with selected suggestion, automatically. If you use "off" you will have to bind command "/%s replace" to a key' % SCRIPT_NAME),
                    'catch_input_completion' : ('on','will catch the input_complete commands [TAB-key]'),
                    'eat_input_char'         : ('on','will eat the next char you type, after replacing a misspelled word'),
                    'suggest_item'           : ('${white}%S${default}', 'item format (%S = suggestion, %D = dict (currently not supported!) colors are allowed with format "${color}")'),
                    'hide_single_dict'       : ('on','will hide dict in item if you have a sinlge dict for buffer only (currently not supported!)'),
                  }

Hooks = {'catch_input_completion': '', 'catch_input_return': ''}
regex_color=re.compile('\$\{([^\{\}]+)\}')
regex_optional_tags=re.compile('%\{[^\{\}]+\}')
multiline_input = 0
# ================================[ weechat options & description ]===============================
def init_options():
    for option,value in OPTIONS.items():
        if not weechat.config_is_set_plugin(option):
            weechat.config_set_plugin(option, value[0])
            weechat.config_set_desc_plugin(option, '%s (default: "%s")' % (value[1], value[0]))
            OPTIONS[option] = value[0]
        else:
            OPTIONS[option] = weechat.config_get_plugin(option)

def toggle_refresh(pointer, name, value):
    global OPTIONS
    option = name[len('plugins.var.python.' + SCRIPT_NAME + '.'):]        # get optionname
    OPTIONS[option] = value                                               # save new value

    if OPTIONS['catch_input_completion'].lower() == "off":
        if Hooks['catch_input_completion']:
            weechat.unhook(Hooks['catch_input_completion'])
            Hooks['catch_input_completion'] = ''
            weechat.unhook(Hooks['catch_input_return'])
            Hooks['catch_input_return'] = ''
    elif OPTIONS['catch_input_completion'].lower() == "on":
        if not Hooks['catch_input_completion']:
            Hooks['catch_input_completion'] = weechat.hook_command_run('/input complete*', 'input_complete_cb', '')
            Hooks['catch_input_return'] = weechat.hook_command_run('/input return', 'input_return_cb', '')

    return weechat.WEECHAT_RC_OK

# ================================[ hooks() ]===============================
# called from command and when TAB is pressed
def auto_suggest_cmd_cb(data, buffer, args):

    input_line = weechat.buffer_get_string(buffer, 'input')
    weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_input_line', '%s' % input_line)

    if args.lower() == 'replace':
        replace_misspelled_word(buffer)
        return weechat.WEECHAT_RC_OK

#    if not weechat.buffer_get_string(buffer,'localvar_spell_correction_suggest_item'):
#        return weechat.WEECHAT_RC_OK

    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)
    if not position:
        position = -1

    # get localvar for misspelled_word and suggestions from buffer or return
    localvar_aspell_suggest = get_localvar_aspell_suggest(buffer)
    if not localvar_aspell_suggest:
        return weechat.WEECHAT_RC_OK

    misspelled_word,aspell_suggestions = localvar_aspell_suggest.split(':')

    aspell_suggestions = aspell_suggestions.replace('/',',')
    aspell_suggestion_list = aspell_suggestions.split(',')
    if len(aspell_suggestion_list) == 0:
        position = -1
        weechat.bar_item_update('spell_correction')
        return weechat.WEECHAT_RC_OK

    # append an empty entry to suggestions to quit without changes.
    if OPTIONS['auto_replace'].lower() == "on":
        aspell_suggestion_list.append('')

    position = int(position)
    # cycle backwards through suggestions
    if args == '/input complete_previous' or args == 'previous':
        # position <= -1? go to last suggestion
        if position <= -1:
            position = len(aspell_suggestion_list)-1
        position -= 1
    # cycle forward through suggestions
    else:
        if position >= len(aspell_suggestion_list)-1:
            position = 0
        else:
            position += 1

    # 2 = TAB or command is called
    weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_item', '%s:%s:%s' % ('2',str(position),aspell_suggestion_list[position]))

    weechat.bar_item_update('spell_correction')
    return weechat.WEECHAT_RC_OK

def show_item_cb (data, item, window):

    buffer = weechat.window_get_pointer(window,"buffer")
    if buffer == '':
        return ''

    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)
    if not position or not aspell_suggest_item:
        return ''

    config_spell_suggest_item = weechat.config_get_plugin('suggest_item')
    if config_spell_suggest_item:
        show_item = config_spell_suggest_item.replace('%S',aspell_suggest_item)
        show_item = substitute_colors(show_item)
        return '%s' % (show_item)
    else:
        return aspell_suggest_item

    # TODO this is for future use in weechat 0.4.1
    # get spell dict
    localvar_aspell_suggest = get_localvar_aspell_suggest(buffer)
    dicts_found = localvar_aspell_suggest.count("/")
    config_spell_suggest_item = weechat.config_get_plugin('suggest_item')
    if dicts_found:
        # localvar_dict = en_GB,de_DE-neu
        dictionary = get_localvar_dict(buffer)
        dictionary_list = dictionary.split(',')
        # more then one dict?
        if len(dictionary_list) > 1:
            undef,aspell_suggestions = localvar_aspell_suggest.split(':')
            dictionary = aspell_suggestions.split('/')
            words = 0
            i = -1
            for a in dictionary:
                i += 1
                words += a.count(',')+1
                if words > int(position):
                    break
            if config_spell_suggest_item:
                show_item = config_spell_suggest_item.replace('%S',aspell_suggest_item)
                show_item = show_item.replace('%D',dictionary_list[i])
                show_item = substitute_colors(show_item)
                return '%s' % (show_item)
            else:
                return aspell_suggest_item
    else:
        if config_spell_suggest_item:
            show_item = config_spell_suggest_item.replace('%S',aspell_suggest_item)
            if weechat.config_get_plugin('hide_single_dict').lower() == 'off':
                show_item = show_item.replace('%D',get_localvar_dict(buffer))
            else:
                show_item = show_item.replace('%D','')
            show_item = substitute_colors(show_item)
            return '%s' % (show_item)
    return aspell_suggest_item

# if a suggestion is selected and you edit input line, then replace misspelled word!
def input_text_changed_cb(data, signal, signal_data):
    global multiline_input

    if multiline_input == '1':
        return weechat.WEECHAT_RC_OK

    buffer = signal_data
    if not buffer:
        return weechat.WEECHAT_RC_OK

    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)
    if not position or not aspell_suggest_item:
        return weechat.WEECHAT_RC_OK

    # 1 = cursor etc., 2 = TAB
    if tab_complete != '0':
        if not aspell_suggest_item:
            aspell_suggest_item = ''
        weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_item', '%s:%s:%s' % ('0',position,aspell_suggest_item))
        weechat.bar_item_update('spell_correction')
        return weechat.WEECHAT_RC_OK

    if OPTIONS['auto_replace'].lower() == "on":
        replace_misspelled_word(buffer) # also remove localvar_suggest_item
        return weechat.WEECHAT_RC_OK

#    weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_item', '%s:%s:' % ('0','-1'))
    weechat.bar_item_update('spell_correction')
    return weechat.WEECHAT_RC_OK

def replace_misspelled_word(buffer):

    input_line = weechat.buffer_get_string(buffer, 'localvar_spell_correction_suggest_input_line')
    if OPTIONS['eat_input_char'].lower() == 'off' or input_line == '':
        input_pos = weechat.buffer_get_integer(buffer,'input_pos')
        # check cursor position
        if len(input_line) < int(input_pos) or input_line[int(input_pos)-1] == ' ' or input_line == '':
            input_line = weechat.buffer_get_string(buffer, 'input')

    weechat.buffer_set(buffer, 'localvar_del_spell_correction_suggest_input_line', '')

    localvar_aspell_suggest = get_localvar_aspell_suggest(buffer)

    # localvar_aspell_suggest = word,word2/wort,wort2
    if localvar_aspell_suggest:
        misspelled_word,aspell_suggestions = localvar_aspell_suggest.split(':')
        aspell_suggestions = aspell_suggestions.replace('/',',')
        aspell_suggestion_list = aspell_suggestions.split(',')
    else:
        return

    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)
    if not position or not aspell_suggest_item:
        return

    position = int(position)

    input_line = input_line.replace(misspelled_word, aspell_suggestion_list[position])
    if input_line[-2:] == '  ':
        input_line = input_line.rstrip()
        input_line = input_line + ' '
            
    weechat.buffer_set(buffer,'input',input_line)
    weechat.bar_item_update('spell_correction')

    # set new cursor position. check if suggestion is longer or smaller than misspelled word
    input_pos = weechat.buffer_get_integer(buffer,'input_pos') + 1
    length_misspelled_word = len(misspelled_word)
    length_suggestion_word = len(aspell_suggestion_list[position])

    if length_misspelled_word < length_suggestion_word:
        difference = length_suggestion_word - length_misspelled_word
        new_position = input_pos + difference + 1
        weechat.buffer_set(buffer,'input_pos',str(new_position))

    weechat.buffer_set(buffer, 'localvar_del_spell_correction_suggest_item', '')

def get_localvar_aspell_suggest(buffer):
    return weechat.buffer_get_string(buffer, 'localvar_aspell_suggest')

def get_localvar_dict(buffer):
    return weechat.buffer_get_string(buffer, 'localvar_aspell_dict')

def substitute_colors(text):
    # substitute colors in output
    return re.sub(regex_color, lambda match: weechat.color(match.group(1)), text)

def get_position_and_suggest_item(buffer):
    if weechat.buffer_get_string(buffer,'localvar_spell_correction_suggest_item'):
        tab_complete,position,aspell_suggest_item = weechat.buffer_get_string(buffer,'localvar_spell_correction_suggest_item').split(':',2)
        return (tab_complete,position,aspell_suggest_item)
    else:
        return ('','','')

def aspell_suggest_cb(data, signal, signal_data):
    buffer = signal_data
    if OPTIONS['auto_pop_up_item'].lower() == 'on':
        auto_suggest_cmd_cb('', buffer, '')
        weechat.buffer_set(buffer, 'localvar_del_spell_correction_suggest_input_line', '')
    return weechat.WEECHAT_RC_OK

# this is a work-around for multiline
def multiline_cb(data, signal, signal_data):
    global multiline_input

    multiline_input = signal_data
#    if multiline_input == '1':
#        buffer = weechat.window_get_pointer(weechat.current_window(),"buffer")
#        input_line = weechat.buffer_get_string(buffer, 'input')
#    else:
#        buffer = weechat.window_get_pointer(weechat.current_window(),"buffer")
#        input_line_bak = weechat.buffer_get_string(buffer, 'input')

#        if input_line != input_line_bak:
#            input_text_changed_cb('','',buffer)

    return weechat.WEECHAT_RC_OK

# ================================[ hook_keys() ]===============================
# TAB key pressed?
def input_complete_cb(data, buffer, command):
    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)
    weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_item', '%s:%s:%s' % ('2',position,aspell_suggest_item))

    localvar_aspell_suggest = get_localvar_aspell_suggest(buffer)
    if not localvar_aspell_suggest:
        return weechat.WEECHAT_RC_OK

    auto_suggest_cmd_cb('', buffer, command)
    return weechat.WEECHAT_RC_OK

# if a suggestion is selected and you press [RETURN] replace misspelled word!
def input_return_cb(data, signal, signal_data):
    buffer = signal

    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)
    if not position or not aspell_suggest_item:
        return weechat.WEECHAT_RC_OK

    if OPTIONS['auto_replace'].lower() == "on" and aspell_suggest_item:
        replace_misspelled_word(buffer)

    return weechat.WEECHAT_RC_OK

# DEL key pressed?
def input_delete_cb(data, signal, signal_data):
    buffer = signal
    weechat.buffer_set(buffer, 'localvar_del_spell_correction_suggest_item', '')
    weechat.buffer_set(buffer, 'localvar_del_spell_correction_suggest_input_line', '')
    weechat.bar_item_update('spell_correction')

#    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)
#    weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_item', '%s:%s:%s' % ('1',position,aspell_suggest_item))
    return weechat.WEECHAT_RC_OK

def input_move_cb(data, signal, signal_data):
    buffer = signal

    tab_complete,position,aspell_suggest_item = get_position_and_suggest_item(buffer)

    localvar_aspell_suggest = get_localvar_aspell_suggest(buffer)
    if not localvar_aspell_suggest:
        return weechat.WEECHAT_RC_OK

    misspelled_word,aspell_suggestions = localvar_aspell_suggest.split(':')

    if not aspell_suggest_item in aspell_suggestions:
        aspell_suggestion_list = aspell_suggestions.split(',',1)
        weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_item', '%s:%s:%s' % ('1',0,aspell_suggestion_list[0]))
        weechat.bar_item_update('spell_correction')
        return weechat.WEECHAT_RC_OK

    weechat.buffer_set(buffer, 'localvar_set_spell_correction_suggest_item', '%s:%s:%s' % ('1',position,aspell_suggest_item))

    return weechat.WEECHAT_RC_OK
# ================================[ main ]===============================
if __name__ == "__main__":
    if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, SCRIPT_DESC, '', ''):
        version = weechat.info_get("version_number", "") or 0

        if int(version) < 0x00040000:
            weechat.prnt('','%s%s %s' % (weechat.prefix('error'),SCRIPT_NAME,': needs version 0.4.0 or higher'))
            weechat.command('','/wait 1ms /python unload %s' % SCRIPT_NAME)

        weechat.hook_command(SCRIPT_NAME, SCRIPT_DESC, 'replace|previous',
                            '\n'
                            'add item "spell_correction" to a bar (i suggest the input bar)\n'
                            '\n'
                            'On an misspelled word, press TAB to cycle through suggestions. Any key on suggestion will replace misspelled word\n'
                            'with current suggestion.\n'
                            '\n'
                            'You have to set "aspell.check.suggestions" to a value >= 0 (default: -1 (off))\n'
                            'Using "aspell.check.real_time" the nick-completion will not work, until all misspelled words in input_line are replaced\n'
                            '\n'
                            'You can bind following commands to key:\n'
                            ' /' + SCRIPT_NAME + '           : to cycle though next suggestion\n'
                            ' /' + SCRIPT_NAME + ' previous  : to cycle though previous suggestion\n'
                            ' /' + SCRIPT_NAME + ' replace   : to replace misspelled word\n'
                            '',
                            '',
                            'auto_suggest_cmd_cb', '')                

        init_options()

        weechat.hook_command_run('/input delete_previous_char', 'input_delete_cb', '')
        weechat.hook_command_run('/input move*', 'input_move_cb', '')
        weechat.hook_signal ('input_text_changed', 'input_text_changed_cb', '')
        # multiline workaround
        weechat.hook_signal('input_flow_free', 'multiline_cb', '')

        weechat.hook_signal ('aspell_suggest', 'aspell_suggest_cb', '')

        if OPTIONS['catch_input_completion'].lower() == "on":
            Hooks['catch_input_completion'] = weechat.hook_command_run('/input complete*', 'input_complete_cb', '')
            Hooks['catch_input_return'] = weechat.hook_command_run('/input return', 'input_return_cb', '')
        weechat.hook_config('plugins.var.python.' + SCRIPT_NAME + '.*', 'toggle_refresh', '')
        weechat.bar_item_new('spell_correction', 'show_item_cb', '')
#        weechat.prnt("","%s" % sys.version_info)
