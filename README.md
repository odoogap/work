# Odoo Workflow Orchestration Engine

Workflow Orchestration Engine is a centralized orchestration server for
running tasks from several different task runner client components.

## Components

**Tasks:** Definition of a job that needs to be accomplished and managed
**Workflow:** Set of tasks and rules that implement a certain chain of execution
**Workflow Orchestration Server:** Centralized management of all workflow
definition as well as all workflow execution.
**Task Runner Client:** Component responsible for the asynchronous execution
of the tasks defined in one or several orchestration engines.

```text
              Orchestration                Orchestration
              Server(OCS)                  Server(OCS)
                 +     +                     +      +
                 |     |                     |      |
                 |     |                     |      |
Task             |     |   Task              |      |     Task
Runner 1  <------+     +-> Runner 2   <------+      +-->  Runner 3
```

It's always the responsibility of the Task Runner to communicate with the
Orchestration server(OCS). OCS will implement processes to monitor the workitems
but it will avoid to interfere with the execution of the Tasks.

## Install

```bash
./odoo/odoo-bin shell -d database -i
```

### Requirements

* Python 2.7
* Odoo - 10.0

## Running a Workflow

Create a test file:

test-1.py:

```python
#!/bin/python
# Workflow has a start parametes json
values = """
{
    "project_id": 189,
    "name": "This is a test task",
    "uid": 1
}
"""
env['work.workflow'].search([('id', '=', 1)]).run_workflow(values, debug=True)

env.cr.commit()
```

Use the test file to start the workflow:

```bash
$> ./odoo/odoo-bin shell -d database < test-1.py
```