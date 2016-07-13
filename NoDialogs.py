import sublime, sublime_plugin
import os
import functools
import threading

VERSION = int(sublime.version())
HOMEDIR = os.path.join(os.path.expanduser("~"), "")

def getParent(path):
	if path.endswith(os.sep):
		return os.path.dirname(os.path.dirname(path))
	else:
		return os.path.dirname(path)

def getPrefixRank(prefix, str):
	rank = 0

	for a, b in zip(prefix, str):
		if a != b:
			return rank
		else:
			rank += 1

	return rank

def getRawCompletions(path):
	dirname = os.path.dirname(path)
	basename = os.path.basename(path)

	if os.path.exists(dirname):
		files = os.listdir(dirname)
		return files

def getCompletions(path, allowDirs=True):
	dirname = os.path.dirname(path)
	basename = os.path.basename(path)

	def isDir(e):
		return os.path.isdir(os.path.join(dirname, e))

	rawCompletions = getRawCompletions(path)
	if not allowDirs:
		rawCompletions = list(filter(lambda e: isDir(e), rawCompletions))

	if basename in rawCompletions:
		return []

	ranked = [(e, 1 if isDir(e) else 0, getPrefixRank(e, basename)) for e in rawCompletions]
	ranked.sort(key=lambda tup: tup[0])               # Sort by name
	ranked.sort(key=lambda tup: tup[1], reverse=True) # Folders first
	ranked.sort(key=lambda tup: tup[2], reverse=True) # Resort by rank

	maxRank = ranked[0][2]
	if maxRank == 0 and basename:
		return []

	completions = []
	for comp, _, rank in ranked:
		if rank < maxRank:
			break

		if allowDirs and isDir(comp):
			completions.append(os.path.join(comp, ''))
		else:
			completions.append(comp)

	return completions

def mkdrip_file(path):
	if not os.path.exists(os.path.dirname(path)):
		os.makedirs(os.path.dirname(path))

def view_putCursor_at_end(view):
	sel = view.sel()
	sel.clear()

	inputEnd = view.size()
	sel.add(sublime.Region(inputEnd, inputEnd))

def view_select_allBut_reverse(view, message):
	sel = view.sel()
	sel.clear()

	inputEnd = view.size()
	sel.add(sublime.Region(inputEnd-len(message), inputEnd))

def forceCloseView(view):
	view.set_scratch(True)
	view.window().run_command('close')

class NoDialogsHelperReplaceCommand(sublime_plugin.TextCommand):
	def run(self, edit, content):
		self.view.replace(edit, sublime.Region(0, self.view.size()), content)

class SublimeDialog(sublime_plugin.TextCommand):
	def __init__(self, view):
		self.accept_modifications = False
		self.oldText = ""

		self.completing = False
		self.acceptDirs = True
		self.completions = []
		self.completionIndex = 0
		self.completionCount = 0

		sublime_plugin.TextCommand.__init__(self, view)

	def defaultDir(self):
		folders = self.window().folders()
		if folders:
			return os.path.join(folders[0], "")
		else:
			return HOMEDIR

	def defaultFile(self):
		if self.view.file_name():
			return self.view.file_name()
		else:
			return os.path.join(self.defaultDir(), self.view.name())

	def window(self):
		return sublime.active_window()

	def completion_setupInput(self):
		self.input.settings().set("auto_complete_commit_on_tab", False)
		self.input.settings().set("tab_completion", False)
		self.input.settings().set("translate_tabs_to_spaces", False)


	def completion_next(self):
		self.completionIndex += 1
		if self.completionIndex == self.completionCount:
			self.completionIndex = 0

		return self.completions[self.completionIndex]

	def completion_setContent(self, base, completion):
		newContent = os.path.join(base, completion)
		self.oldText = newContent

		self.input.run_command('sublime_dialogs_helper_replace', {'content': newContent})


	def on_modified(self, text):
		if not self.accept_modifications:
			return

		sel = self.input.sel()[0]
		text = self.input.substr(sublime.Region(0, sel.begin()))

		if text.endswith('\t'):
			path = text[:-1]

			if self.completing and self.completionCount > 1 and self.oldText == path:
				self.completion_setContent(getParent(path), self.completion_next())
				return

			self.completions = getCompletions(path, self.acceptDirs)
			if self.completions:
				self.completing = True
				self.completionIndex = 0
				self.completionCount = len(self.completions)

				self.completion_setContent(os.path.dirname(path), self.completions[0])
			else:
				self.completing = False
				self.oldText = ''

				self.input.run_command('open_prompt_replace', {'content': path})
		elif self.oldText != text:
			self.completing = False
			self.oldText = ''


#
# Open
#
class NoDialogsCreateOpenPromptCommand(SublimeDialog):
	def __init__(self, view):
		self.input = None
		SublimeDialog.__init__(self, view)

	def on_open_inputEnd(self, path):
		self.window().open_file(path)

	def run(self, edit):
		self.input = self.window().show_input_panel("Open:", self.defaultDir(), self.on_open_inputEnd, self.on_modified, None)

		sel = self.input.sel()
		sel.clear()

		selStart = len(HOMEDIR)
		inputEnd = self.input.size()
		sel.add(sublime.Region(selStart, inputEnd))

		self.completion_setupInput()
		self.accept_modifications = True


#
# Save
#
class SaveAsThread(threading.Thread):
	def __init__(self, view, window, path, callback):
		self.view = view
		self.window = window
		self.path = path
		self.callback = callback
		threading.Thread.__init__(self)

	def run(self):
		mkdrip_file(self.path)

		with open(self.path, 'w', encoding='utf8') as f:
			f.write(self.view.substr(sublime.Region(0, self.view.size())))

		forceCloseView(self.view)
		self.window.open_file(self.path)

		self.window.run_command('hide_panel')

		self.callback()

class MkdripSaveThread(threading.Thread):
	def __init__(self, view, path, callback):
		self.view = view
		self.path = path
		self.callback = callback
		threading.Thread.__init__(self)

	def run(self):
		mkdrip_file(self.path)
		self.view.run_command("save")

		self.callback()

class Send2TrashThread(threading.Thread):
	def __init__(self, path, callback):
		self.callback = callback
		self.path = path
		threading.Thread.__init__(self)

	def run(self):
		if VERSION < 3000:
			from send2trash import send2trash # ST2
		else:
			from .send2trash import send2trash # ST3

		send2trash(self.path)

		self.callback()

class NoDialogsCreateGenericSavePrompt(SublimeDialog):
	def saveAs(self, path):
		self.beforeSaveHook(path)
		SaveAsThread(self.view, self.window(), path, functools.partial(self.afterSaveHook, path)).start()

	def overwrite_ifAnswerPositive(self, path, ans):
		if (not ans) or ("NnFf".find(ans[0]) == -1):
			Send2TrashThread(path, functools.partial(self.saveAs, path)).start()

	def on_saveTo_inputEnd(self, inputPath):
		if os.path.isdir(inputPath):
			message = "untitled"
			placeholder = os.path.join(self.defaultDir(), message)

			self.input = self.window().show_input_panel("Save:", placeholder, self.on_saveTo_inputEnd, self.on_modified, None)
			view_select_allBut_reverse(self.input, message)

			self.completion_setupInput()
			self.accept_modifications = True
		else:
			if os.path.lexists(inputPath):
				query = "Overwrite? (Y/y T/t N/n F/f) (defaults to YES):"
				onDone = functools.partial(self.overwrite_ifAnswerPositive, inputPath)

				self.window().show_input_panel(query, "", onDone, None, None)
			else:
				self.saveAs(inputPath)

	def run(self, edit):
		return

	def beforeSaveHook(self, path):
		return

	def afterSaveHook(self, path):
		return

class NoDialogsCreateSavePromptCommand(NoDialogsCreateGenericSavePrompt):
	def resave(self, path):
		self.view.set_status("NoDialogs_resave", "Saving changes: "+os.path.basename(path))

		MkdripSaveThread(self.view, path, functools.partial(self.view.erase_status, "NoDialogs_resave")).start()

	def run(self, edit):
		curPath = self.view.file_name()
		if curPath:
			self.resave(curPath)
		else:
			self.input = self.window().show_input_panel("Save:", self.defaultFile(), self.on_saveTo_inputEnd, self.on_modified, None)
			view_putCursor_at_end(self.input)

			self.completion_setupInput()
			self.accept_modifications = True

	def beforeSaveHook(self, path):
		self.view.set_status("NoDialogs_save", "Saving: "+os.path.basename(path))

	def afterSaveHook(self, path):
		self.view.erase_status("NoDialogs_save")

class NoDialogsCreateCopyPromptCommand(NoDialogsCreateGenericSavePrompt):
	def run(self, edit):
		self.input = self.window().show_input_panel("Copy:", self.defaultFile(), self.on_saveTo_inputEnd, self.on_modified, None)
		view_select_allBut_reverse(self.input, os.path.basename(self.defaultFile()))

		self.completion_setupInput()
		self.accept_modifications = True

	def beforeSaveHook(self, path):
		self.view.set_status("NoDialogs_copy", "Copying: "+os.path.basename(path))

	def afterSaveHook(self, path):
		self.view.erase_status("NoDialogs_copy")
		# Send2TrashThread(path, functools.partial(self.view.erase_status, "NoDialogs_copy")).start()

class NoDialogsCreateMovePromptCommand(NoDialogsCreateGenericSavePrompt):
	def run(self, edit):
		curPath = self.defaultFile()
		self.oldPath = curPath

		self.input = self.window().show_input_panel("Move:", curPath, self.on_saveTo_inputEnd, self.on_modified, None)
		view_select_allBut_reverse(self.input, os.path.basename(curPath))

		self.completion_setupInput()
		self.accept_modifications = true

	def beforeSaveHook(self, path):
		self.view.set_status("NoDialogs_move", "Moving: "+os.path.basename(path))

	def afterSaveHook(self, path):
		Send2TrashThread(self.oldPath, functools.partial(self.view.erase_status, "NoDialogs_move")).start()


#
# Delete
#

class NoDialogsCreateDeletePromptCommand(SublimeDialog):
	def closeView_ifAnswerPositive(self, ans):
		if (not ans) or ("YyTt".find(ans[0]) == -1):
			return

		forceCloseView(self.view)

	def run(self, edit):
		curPath = self.view.file_name()
		if curPath and os.path.exists(curPath):
			def callback():
				self.view.erase_status("NoDialogs_delete")

				self.view.set_status("NoDialogs_deleteOk", "Moved to trash: "+os.path.basename(curPath))
				threading.Timer(2.0, functools.partial(self.view.erase_status, "NoDialogs_deleteOk"), None).start()

			self.view.set_status("NoDialogs_delete", "Deleting: "+os.path.basename(curPath))
			Send2TrashThread(curPath, callback).start()
		else:
			self.window().show_input_panel("Discard? (Y/y T/t N/n F/f) (defaults to NO):", "", functools.partial(self.closeView_ifAnswerPositive), None, None)


#
# Close tab
#

class NoDialogsCreateClosePromptCommand(SublimeDialog):
	def closeView_ifAnswerPositive(self, ans):
		if (not ans) or ("YyTt".find(ans[0]) == -1):
			forceCloseView(self.view)

	def run(self, edit):
		if self.view.is_dirty():
			self.window().show_input_panel("Discard? (Y/y T/t N/n F/f) (defaults to YES):", "", functools.partial(self.closeView_ifAnswerPositive), None, None)
		else:
			self.window().run_command('close')

