import sublime, sublime_plugin
import os
import errno

ST2 = int(sublime.version()) < 3000

if ST2:
	from send2trash import send2trash
else:
	from .send2trash import send2trash

#
# Helpers
#
def mkdirp(path):
	try:
		os.makedirs(os.path.dirname(path))
	except OSError as e:
		if not e.errno == errno.EEXIST:
			raise
		else:
			pass

def ensure_path_sep_at_end(path):
	return os.path.join(path, '')

def ensure_path_sep_at_end_of_folders(path):
	if os.path.isdir(path):
		return ensure_path_sep_at_end(path)
	else:
		return path

def can_resave(view):
	return view.file_name() is not None

def all_region(view):
	return sublime.Region(0, view.size())

def read_view(view):
	return view.substr(all_region(view))

def write_view_to_file(view, path):
	mkdirp(path)

	if ST2:
		with open(path, 'w') as fd:
			fd.write(read_view(view))

		sublime.status_message('Saved: '+path)
	else:
		view_encoding = view.encoding()
		save_encoding = view_encoding if view_encoding != 'Undefined' else 'UTF-8'
		with open(path, 'w', encoding = save_encoding) as fd:
			fd.write(read_view(view))

		sublime.status_message('Saved: '+path+' ('+save_encoding+')')

def force_close_view(view):
	view.set_scratch(True)

	win = view.window()
	win.focus_view(view)
	win.run_command('close')

def set_currently_running_command(cmd):
	global currently_running_command
	currently_running_command = cmd

# Homedir handling
def expand_homedir(path):
	return os.path.expanduser(path)

def abbr_homedir(path):
	return path.replace(HOMEDIR, HOMEDIR_ABBR)

HOMEDIR = ensure_path_sep_at_end(os.path.expanduser('~'))
HOMEDIR_ABBR = ensure_path_sep_at_end('~')


#
# General
#
settings = {}
def plugin_loaded():
    global settings
    settings = sublime.load_settings('NoDialogs.sublime-settings')

if ST2:
	plugin_loaded()

class NoDialogsReplaceHelperCommand(sublime_plugin.TextCommand):
	def run(self, edit, new_text):
		self.view.replace(edit, all_region(self.view), new_text)


#
# Autocomplete
#
def autocomplete_file_name(raw_path):
	path = expand_homedir(raw_path)

	path_parts = path.rsplit(os.sep, 1)
	dirname = path_parts[0]
	basename = path_parts[1]

	files = []
	for file in os.listdir(dirname):
		if os.path.isdir(os.path.join(dirname, file)):
			files.append(ensure_path_sep_at_end(file))
		else:
			files.append(file)

	if basename in files:
		return [basename]
	if not basename and not settings.get('no_dialogs_use_shell_like_autocomplete'):
		return files

	# Ranking
	def apathy_ranker(_):
		return 0

	def dir_lover_ranker(filename):
		return 1 if os.path.isdir(os.path.join(dirname, file)) else 0

	def dir_hater_ranker(filename):
		return 1-dir_lover_ranker(filename)

	def prefix_ranker(filename):
		rank = 0
		for a, b in zip(basename, filename):
			if a != b:
				return rank
			else:
				rank += 1
		return rank

	def terminal_ranker(filename):
		return 1 if filename.startswith(basename) else 0

	ranker = prefix_ranker
	dir_ranker = apathy_ranker
	if settings.get('no_dialogs_use_shell_like_autocomplete'):
		ranker = terminal_ranker

	folder_priority = settings.get('no_dialogs_folders_first')
	if folder_priority == 'first':
		dir_ranker = dir_lover_ranker
	elif folder_priority == 'last':
		dir_ranker = dir_hater_ranker

	ranked = [(ranker(file), file, dir_ranker(file)) for file in files]

	if not settings.get('no_dialogs_use_shell_like_autocomplete'):
		ranked.sort(key = lambda entry: entry[2], reverse=True) # Folder priority
	ranked.sort(key = lambda entry: entry[0], reverse=True) # Sort by rank

	# Leave only entries with maximum rank
	max_ranked = []
	max_rank = ranked[0][0]
	if max_rank != 0:
		for rank, filename, _ in ranked:
			if rank < max_rank:
				break

			max_ranked.append(filename)
	else:
		max_ranked = [entry[1] for entry in ranked]

	if settings.get('no_dialogs_use_shell_like_autocomplete'):
		prefix = os.path.commonprefix(max_ranked)
		if not prefix:
			return [basename]
		else:
			return [prefix]
	else:
		max_ranked.sort() # Sort by name

		return max_ranked

def autocomplete_path(path):
	dirname = abbr_homedir(os.path.dirname(path))

	return [os.path.join(dirname, completion) for completion in autocomplete_file_name(path)]

def update_currently_open_prompt(view):
	global currently_open_prompt
	currently_open_prompt = view

	global history_index
	history_index = -1 # when prompt changes history has to start over

	global glob_change_count
	glob_change_count = 0

def replace_view_text_with_edit(view, edit, new_text):
	view.replace(edit, all_region(view), new_text)

	size = view.size()
	sel = view.sel()
	sel.clear()
	sel.add(sublime.Region(size, size))

def replace_view_text(view, new_text):
	view.run_command('no_dialogs_replace_helper', {'new_text': new_text})

def replace_prompt_text(new_text):
	replace_view_text(currently_open_prompt, new_text)

next_completion = False
class NoDialogsAutocompleteNextCommand(sublime_plugin.TextCommand):
	def run(self, _):
		global next_completion
		next_completion = True

		self.view.run_command(settings.get('no_dialogs_right_arrow_default_command'), settings.get('no_dialogs_right_arrow_default_args'))

if ST2:
	glob_change_count = 0
def modification_counter(_):
	if not ST2:
		return

	global glob_change_count
	glob_change_count += 1

class NoDialogsTabTriggerCommand(sublime_plugin.TextCommand):
	def __init__(self, view):
		self.last_change_count = None
		self.completions = None
		self.completions_count = None
		self.last_completion_index = None

		sublime_plugin.TextCommand.__init__(self, view)

	def run(self, edit):
		if settings.get('no_dialogs_autocomplete_mode') != 'tab_trigger':
			return

		text = read_view(self.view)

		if ST2:
			global glob_change_count
			view_change_count = glob_change_count
		else:
			view_change_count = self.view.change_count()

		global next_completion
		if next_completion:
			self.last_change_count = None
			next_completion = False

		def handle_first_completion():
			self.last_change_count = view_change_count
			self.completions = autocomplete_path(text)
			self.completions_count = len(self.completions)
			self.last_completion_index = 0

			replace_prompt_text(self.completions[self.last_completion_index])

			if self.completions_count == 1:
				self.last_change_count = None

		if self.last_change_count is None:
			handle_first_completion()
		elif view_change_count - self.last_change_count <= 1:
			self.last_change_count = view_change_count

			self.last_completion_index += 1
			if self.last_completion_index >= self.completions_count:
				self.last_completion_index = 0

			replace_prompt_text(self.completions[self.last_completion_index])
		else:
			self.last_change_count = None
			self.completions = None
			self.completions_count = None
			self.last_completion_index = None

			handle_first_completion()




#
# History
#
COMMANDS = ['save', 'copy', 'move', 'open']
global_history = []
save_history = []
copy_history = []
move_history = []
history_index = -1
history_current_edit = None

def add_to_history(entry):
	history_current_edit = None

	if currently_running_command is None:
		print('[NoDialogs] !FIXME! No command is running, yet history is being updated')
		return

	if settings.get('no_dialogs_use_global_history'):
		if currently_running_command not in COMMANDS:
			print('[NoDialogs] !FIXME! Unknown command is running '+currently_running_command)

		global global_history
		global_history.insert(0, entry)
		return

	if currently_running_command == 'save':
		global save_history
		save_history.insert(0, entry)
	elif currently_running_command == 'copy':
		global copy_history
		copy_history.insert(0, entry)
	elif currently_running_command == 'move':
		global move_history
		move_history.insert(0, entry)
	else:
		print('[NoDialogs] !FIXME! Unknown command is running '+currently_running_command)
		if currently_running_command not in COMMANDS:
 			print('[NoDialogs] !FIXME! Command is in COMMANDS, but not handled properly by add_to_history '+currently_running_command)

def retrive_history():
	if currently_running_command is None:
		print('[NoDialogs] !FIXME! No command is running, yet history is being read')
		return

	history = None

	if settings.get('no_dialogs_use_global_history'):
		if currently_running_command not in COMMANDS:
			print('[NoDialogs] !FIXME! Unknown command is running '+currently_running_command)

		global global_history
		history = global_history
	elif currently_running_command == 'save':
		global save_history
		history = save_history
	elif currently_running_command == 'copy':
		global copy_history
		history = copy_history
	elif currently_running_command == 'move':
		global move_history
		history = move_history
	else:
		print('[NoDialogs] !FIXME! Unknown command is running '+currently_running_command)
		if currently_running_command not in COMMANDS:
			print('[NoDialogs] !FIXME! Command is in COMMANDS, but not handled properly by add_to_history '+currently_running_command)
		return

	return history

def read_from_history(index):
	return retrive_history()[index]

def history_size():
	return len(retrive_history())

class NoDialogsHistoryPreviousCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		if not settings.get('no_dialogs_allow_history'):
			return
		if currently_running_command not in settings.get('no_dialogs_allow_history_in'):
			return

		global history_index

		hist_size = history_size()
		if hist_size == 0:
			return

		global history_current_edit
		if history_index == -1:
			history_current_edit = read_view(self.view)

		history_index += 1
		if history_index >= hist_size:
			if settings.get('no_dialogs_cycle_history'):
				history_index = -1
			else:
				history_index = hist_size-1

		if history_index == -1:
			new_text = history_current_edit
		else:
			new_text = read_from_history(history_index)

		replace_view_text_with_edit(self.view, edit, new_text)

class NoDialogsHistoryNextCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		if not settings.get('no_dialogs_allow_history'):
			return
		if currently_running_command not in settings.get('no_dialogs_allow_history_in'):
			return

		global history_index

		hist_size = history_size()
		if hist_size == 0:
			return

		history_index -= 1
		if history_index < -1:
			if settings.get('no_dialogs_cycle_history'):
				history_index = hist_size-1
			else:
				history_index = -1

		global history_current_edit
		if history_index == -1:
			new_text = history_current_edit
		else:
			new_text = read_from_history(history_index)

		replace_view_text_with_edit(self.view, edit, new_text)

#
# Save commands
#
class NoDialogsCreateSavePromptCommand(sublime_plugin.ApplicationCommand):
	def __init__(self):
		self.window = None
		self.view = None

		self.prompt = None
		self.path = None

		sublime_plugin.ApplicationCommand.__init__(self)

	#
	# Helpers
	def resave(self):
		mkdirp(self.view.file_name())
		self.view.run_command('save')

	def update_prompt(self, prompt):
		self.prompt = prompt
		update_currently_open_prompt(self.prompt)

	def alias_window_and_view(self):
		self.window = sublime.active_window()
		self.view = self.window.active_view()

	def cleanup(self):
		self.window = None
		self.view = None

		self.update_prompt(None)
		self.path = None

	def reopen_from_new_path(self):
		force_close_view(self.view)
		self.window.open_file(self.path)
		self.window.run_command('hide_panel')

	def trash_file(self):
		send2trash(self.path)

	#
	# Subroutines
	def probable_dirname_and_basename(self):
		basename = ''
		dirname = HOMEDIR

		view_name = self.view.name()
		if view_name is not None and view_name:
			basename = view_name
		elif settings.get('no_dialogs_use_untitled_files'):
			basename = settings.get('no_dialogs_untitled_file_name')

		open_folders = self.window.folders()
		if open_folders is not None and open_folders:
			dirname = ensure_path_sep_at_end(open_folders[0])

		return (abbr_homedir(dirname), basename)

	def finish_the_job(self):
		add_to_history(abbr_homedir(self.path))

		write_view_to_file(self.view, self.path)
		self.reopen_from_new_path()

		self.cleanup()

	#
	# Event handlers
	def on_overwrite_answer(self, answer):
		if not answer:
			answer = settings.get('no_dialogs_overwrite_by_default')

		if 'Nn'.find(answer[0]) != -1:
			self.cleanup()
			return

		self.trash_file() # move overwritten file to trash
		self.finish_the_job()

	def on_done(self, path):
		self.path = expand_homedir(ensure_path_sep_at_end_of_folders(path))

		if os.path.isdir(self.path):
			self.cleanup()
			self.alias_window_and_view()
			self.create_prompt(path, settings.get('no_dialogs_untitled_file_name'))
			return

		if os.path.exists(self.path):
			prompt = 'File exists. Overwrite? (defaults to '+settings.get('no_dialogs_overwrite_by_default')+')'
			self.window.show_input_panel(prompt, '', self.on_overwrite_answer, modification_counter, self.cleanup)
			return

		self.finish_the_job()

	def on_cancel(self):
		self.cleanup()

	#
	# Main code
	PROMPT = 'Save:'
	def create_prompt(self, prefix, selected_text):
		prefix = abbr_homedir(prefix)

		default_text = os.path.join(prefix, selected_text) if selected_text else prefix
		self.update_prompt(self.window.show_input_panel(self.PROMPT, default_text, self.on_done, modification_counter, self.on_cancel))

		if selected_text:
			size = self.prompt.size()
			sel = self.prompt.sel()
			sel.clear()
			sel.add(sublime.Region(size - len(selected_text), size))

	COMMAND_NAME = 'save'
	def pre_run(self):
		self.cleanup()
		set_currently_running_command(self.COMMAND_NAME)
		self.alias_window_and_view()

	def run(self):
		self.pre_run()

		if can_resave(self.view):
			self.resave()
			return

		(dirname, basename) = self.probable_dirname_and_basename()
		self.create_prompt(dirname, basename)

class NoDialogsCreateCopyPromptCommand(NoDialogsCreateSavePromptCommand):
	PROMPT = 'Save copy as:'
	COMMAND_NAME = 'copy'
	def finish_the_job(self):
		add_to_history(abbr_homedir(self.path))

		write_view_to_file(self.view, self.path)
		self.cleanup()

	def run(self):
		self.pre_run()

		if not can_resave(self.view):
			(dirname, basename) = self.probable_dirname_and_basename()
			self.create_prompt(dirname, basename)
			return

		view_file_name = self.view.file_name()
		self.create_prompt(view_file_name, '')

		(_, basename) = os.path.split(view_file_name)
		(__, extname) = os.path.splitext(basename)

		size = self.prompt.size()
		sel = self.prompt.sel()
		sel.clear()
		sel.add( sublime.Region(size - len(basename), size - len(extname)) )

class NoDialogsCreateMovePromptCommand(NoDialogsCreateCopyPromptCommand):
	PROMPT = 'Move to:'
	COMMAND_NAME = 'move'
	def finish_the_job(self):
		add_to_history(abbr_homedir(self.path))

		view_file_name = self.view.file_name() # destroy old copy
		if view_file_name:
			send2trash(view_file_name)

		write_view_to_file(self.view, self.path)
		self.reopen_from_new_path()

		self.cleanup()


#
# Close commands
#
class NoDialogsCreateClosePromptCommand(sublime_plugin.ApplicationCommand):
	def __init__(self):
		self.window = None
		self.view = None

		self.last_focused_view = None
		self.save_on_focus_lost_was = None

		sublime_plugin.ApplicationCommand.__init__(self)

	def cleanup(self):
		if self.last_focused_view is not None:
			self.window.focus_view(self.last_focused_view)
		self.view.settings().set('save_on_focus_lost', self.save_on_focus_lost_was)

		self.window = None
		self.view = None

		self.last_focused_view = None
		self.save_on_focus_lost_was = None

	def alias_window_and_view(self):
		self.window = sublime.active_window()
		self.view = self.window.active_view()

	def finish_the_job(self):
		self.view.settings().set('save_on_focus_lost', False)
		force_close_view(self.view)

		self.cleanup()

	def on_overwrite_answer(self, answer):
		if not answer:
			answer = settings.get(self.DISCARD_SETTING)

		if 'Nn'.find(answer[0]) != -1:
			self.cleanup()
			return

		self.finish_the_job()

	def will_closing_discard(self, view):
		if view is None:
			return False

		view_file_name = self.view.file_name()
		return self.view.is_dirty() or view_file_name and not os.path.exists(view_file_name)

	DISCARD_SETTING = 'no_dialogs_discard_by_default'
	def show_discard_prompt(self):
		view_settings = self.view.settings()
		self.save_on_focus_lost_was = view_settings.get('save_on_focus_lost')
		view_settings.set('save_on_focus_lost', False)

		self.window.show_input_panel('Discard? (defaults to '+settings.get(self.DISCARD_SETTING)+')', '', self.on_overwrite_answer, modification_counter, self.cleanup)

	def run(self):
		self.alias_window_and_view()

		if self.will_closing_discard(self.view):
			self.show_discard_prompt()
			return

		self.window.run_command('close')

class NoDialogsCreateCloseWindowPromptCommand(NoDialogsCreateClosePromptCommand):
	DISCARD_SETTING = 'no_dialogs_discard_in_window_by_default'
	def finish_the_job(self):
		self.view.set_scratch(True)
		self.view.settings().set('save_on_focus_lost', False)

		self.cleanup()
		sublime.run_command('no_dialogs_create_close_window_prompt')

	def run(self):
		self.window = sublime.active_window()

		for view in self.window.views():
			self.view = view

			if not self.will_closing_discard(view):
				continue

			self.last_focused_view = self.window.active_view()
			self.window.focus_view(view)

			self.show_discard_prompt()
			return # wait for input, then start over

		self.window.run_command('close_window')

class NoDialogsCreateExitPromptCommand(NoDialogsCreateClosePromptCommand):
	DISCARD_SETTING = 'no_dialogs_discard_on_exit_by_default'
	def finish_the_job(self):
		self.view.set_scratch(True)
		self.view.settings().set('save_on_focus_lost', False)

		self.cleanup()
		sublime.run_command('no_dialogs_create_exit_prompt')

	def run(self):
		for win in sublime.windows():
			self.window = win
			for view in self.window.views():
				self.view = view

				if not self.will_closing_discard(view):
					continue

				self.last_focused_view = self.window.active_view()
				self.window.focus_view(view)

				self.show_discard_prompt()
				return # wait for input, then start over

		sublime.run_command('exit')


#
# Rest of the commands
#

class NoDialogsCreateDeletePromptCommand(sublime_plugin.ApplicationCommand):
	def __init__(self):
		self.window = None
		self.view = None

		sublime_plugin.ApplicationCommand.__init__(self)

	def cleanup(self):
		self.window = None
		self.view = None

	def alias_window_and_view(self):
		self.window = sublime.active_window()
		self.view = self.window.active_view()

	def finish_the_job(self):
		send2trash(self.view.file_name())
		if settings.get('no_dialogs_close_on_deletion'):
			force_close_view(self.view)

		self.cleanup()

	def on_overwrite_answer(self, answer):
		if not answer:
			answer = settings.get('no_dialogs_delete_by_default')

		if 'Nn'.find(answer[0]) != -1:
			self.cleanup()
			return

		self.finish_the_job()

	def show_prompt(self):
		self.window.show_input_panel('Delete? (defaults to '+settings.get('no_dialogs_delete_by_default')+')', '', self.on_overwrite_answer, modification_counter, self.cleanup)

	def run(self):
		self.alias_window_and_view()

		view_file_name = self.view.file_name()
		if not view_file_name or not os.path.exists(view_file_name):
			sublime.run_command('no_dialogs_create_close_prompt')
			return

		if not settings.get('no_dialogs_delete_without_prompt'):
			self.show_prompt()
		else:
			self.finish_the_job()

class NoDialogsCreateOpenPrompt(sublime_plugin.ApplicationCommand):
	def __init__(self):
		self.window = None
		self.view = None

		self.prompt = None
		self.path = None

		sublime_plugin.ApplicationCommand.__init__(self)

	def alias_window_and_view(self):
		self.window = sublime.active_window()
		self.view = self.window.active_view()

	def cleanup(self):
		self.window = None
		self.view = None

		self.update_prompt(None)
		self.path = None

	def update_prompt(self, prompt):
		self.prompt = prompt
		update_currently_open_prompt(self.prompt)

	def probable_dirname_and_basename(self):
		basename = ''
		dirname = HOMEDIR

		view_file_name = self.view.file_name()
		if view_file_name:
			return (abbr_homedir(ensure_path_sep_at_end(os.path.dirname(view_file_name))), os.path.basename(view_file_name))

		view_name = self.view.name()
		if view_name is not None and view_name:
			basename = view_name

		open_folders = self.window.folders()
		if open_folders is not None and open_folders:
			dirname = ensure_path_sep_at_end(open_folders[0])

		return (abbr_homedir(dirname), basename)

	def on_done(self, path):
		self.path = expand_homedir(ensure_path_sep_at_end_of_folders(path))

		add_to_history(abbr_homedir(self.path))

		if os.path.isdir(self.path):
			project = self.window.project_data()

			if project:
				if project["folders"]:
					for folder in project["folders"]:
						if folder["path"] and folder["path"] == path:
							return

					project["folders"].append({"path": path})
				else:
					project["folders"] = [path]
			else:
				project = {"folders": [{"path": path}]}

			self.window.set_project_data(project)

			self.cleanup()
			return

		self.window.open_file(path)
		self.cleanup()

	def on_cancel(self):
		self.cleanup()

	def create_prompt(self, prefix, selected_text):
		prefix = abbr_homedir(prefix)

		default_text = os.path.join(prefix, selected_text) if selected_text else prefix
		self.update_prompt(self.window.show_input_panel('Open:', default_text, self.on_done, modification_counter, self.on_cancel))

		if selected_text:
			size = self.prompt.size()
			sel = self.prompt.sel()
			sel.clear()
			sel.add(sublime.Region(size - len(selected_text), size))

	def run(self):
		self.cleanup()
		set_currently_running_command('open')
		self.alias_window_and_view()

		(dirname, basename) = self.probable_dirname_and_basename()
		self.create_prompt(dirname, basename)


#
# Event listener
#
currently_open_prompt = None
currently_running_command = None
class NoDialogsEventListener(sublime_plugin.EventListener):
	def on_query_completions(self, view, prefix, locations):
		if settings.get('no_dialogs_autocomplete_mode') != 'default':
			return
		if currently_open_prompt is None or currently_open_prompt != view:
			return

		comps = autocomplete_file_name(read_view(view))
		flags = 0
		flags |= sublime.INHIBIT_WORD_COMPLETIONS if settings.get('no_dialogs_inhibit_word_completions') else 0
		flags |= sublime.INHIBIT_EXPLICIT_COMPLETIONS if settings.get('no_dialogs_inhibit_explicit_completions') else 0

		return ([[comp, comp] for comp in comps], flags)

	def on_query_context(_, __, key, ___, ____, _____):
		if key == 'no_dialogs_prompt_open' and currently_open_prompt is not None:
			return True
		elif key == 'no_dialogs_no_shell_like_autocomplete' and not settings.get('no_dialogs__shell_like_autocomplete'):
			return True
		elif key == 'no_dialogs_right_arrow_override' and settings.get('no_dialogs_right_arrow_override') and currently_running_command in ['save', 'copy', 'move', 'open']:
			return True
		elif key == 'no_dialogs_allow_history' and settings.get('no_dialogs_allow_history') and currently_running_command in settings.get('no_dialogs_allow_history_in'):
			return True
