import os
import sys
sys.path.insert(0, os.path.abspath('..'))

project = 'async-cache'
copyright = '2024, async-cache contributors'
author = 'Rajat Singh et al.'
release = '2.0'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

autodoc_typehints = 'description'
autodoc_member_order = 'bysource'
