## NoDialogs
ND is a plugin for ST3. It was not tested on ST2, but you can give it a whirl.

ND removes modal dialogs. It replaces them with input panels. It does so by overriding key bindings most oftenly causing modal dialogs to appear.

ND also includes a couple of brand new features. It lets you delete and move files from ST.

ND supports autocompletion in its input panels. ND remembers the history of used files in its input panels.

Every function ND provides (including README, LICENSE and config files) is in the Command Pallete.

Every file ND "removes" or "deletes" is actually send to trash using [`send2trash`](https://github.com/hsoft/send2trash) python module.

## Installation
https://packagecontrol.io/packages/NoDialogs

## Replaced dialogs
* Open dialog
* Save dialog
* Save as dialog
* Close file discard prompt
* Close window discard prompt
* Exit discard prompt
* Add folder to project dialog

## Additional features
* Current file deletion
* Moving current file (changing the name to a new one)

## Key bindings overriden
In each keybinding `super` is replaced by `ctrl` on Windows

Key binding     | Description
--------------- | -----------
`super+o`       | "Open" prompt
`super+s`       | "Save" prompt
`super+shift+s` | "Copy" prompt (aka "Save as")
`super+alt+s`   | "Move" prompt (aka "Rename")
`super+w`       | "Close" prompt (aka "Close tab")
`super+shift+w` | "Close window" prompt
`super+q`       | "Exit" prompt (aka "Quit")
`super+alt+d`   | "Delete" prompt

## Settings
See [settings file](#NoDialogs.sublime-settings)
