# -*- coding: utf-8 -*-
{
    'name': "Workflow Engine",

    'application': True,

    'summary': """
        Workflow Engine
    """,

    'description': """
Workflow Engine
===============

Workflows consist of related process sets that will be triggered by a user or by a specific event.

> e.g user will see in the project form a button that says "Start a Workflow"
> after that he will see a pop-up with a list of available workflows and a proceed button

Events will be defined in the workflow form, stating the conditions how they can be triggered.

> e.g. account balance grows beyond a certain value or a certain date is due
> Workflows define sets of actions: jobs(automated) or tasks(human driven)

Each action will define it's predecessors and ancestors, with the possibility to create lags(days)

Jobs will have a specific list of possible types: run_some_api, create_note, send_email ...

    """,

    'author': "Diogo Duarte",
    'website': "http://diogocduarte.github.io",

    'category': 'Specific Industry Applications',
    'version': '0.1',

    'depends': ['project'],

    'data': [
        'security/ir.model.access.csv',
        'views/workflow_views.xml',
        'views/workitems_views.xml',
        'views/management_views.xml',
        'data/workflow_job.xml'
    ],
    'qweb': [],

    'demo': [
    ],
}
