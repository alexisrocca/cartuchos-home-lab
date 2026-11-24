moduledir = python_dir / 'cartridges'

configure_file(
  input: 'cartridges.in',
  output: 'cartridges',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
)

install_subdir('importer', install_dir: moduledir)
install_subdir('utils', install_dir: moduledir)
install_subdir('store', install_dir: moduledir)
install_subdir('logging', install_dir: moduledir)
install_subdir('errors', install_dir: moduledir)
install_data(
  [
    'application_delegate.py',
    'main.py',
    'window.py',
    'preferences.py',
    'details_dialog.py',
    'game.py',
    'game_cover.py',
    'remote_progress.py',
    'remote_migration.py',
    'remote_stream.py',
    'remote_power.py',
    'home_lab_stages.py',
    configure_file(input: 'shared.py.in', output: 'shared.py', configuration: conf),
  ],
  install_dir: moduledir,
)
