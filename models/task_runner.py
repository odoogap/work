# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools
from odoo.exceptions import ValidationError

from dateutil.relativedelta import relativedelta
import logging


_logger = logging.getLogger(__name__)


class WorkflowJobManager(models.TransientModel):
    """This is the inbuilt Task Runner Client

    This client component is triggered by a scheduled action
    should be used for development purposes or can be used
    if the tasks are just ran on the same server for
    simple use cases.

    The most comment situation will be running this client
    in a remote machine, near the data source or near to the
    integrated system, for security or performance reasons.

    """
    _name = "work.workflow.job.manager"
    # _auto = False

    @api.model
    def manage_jobs(self, host, debug=False,):
        """ Workflow Job Manager will check workitems and will trigger transitions to create new workitems

        This method will not start any workflow, it will only maintain the existing workitem flow.
        To start the workflow instance, other mechanisms will be used
           (e.g.
              * on object create/delete/update
              * on button press
              * on sensor detection
              * other)

        Basic steps of any
            * Check jobs - active ones: not done or cancel
            * Trigger transactions - completed, not triggered
            * Close completed instances

        """

        # This client might not be capable of doing all type of jobs
        # this is why we need a selector
        job_type_selector = 'work.workflow.job'

        # Check jobs - active ones: not done or cancel
        workitems_to_check = self.env['work.workflow.workitem'].search([
            ('job_type', 'ilike', job_type_selector),
            ('state', 'not in', ['done', 'canceled'])
        ])
        print "------------- manage", workitems_to_check

        for wk in workitems_to_check:
            # Run the postponed jobs
            if wk.state == 'running' and not wk.run:
                wk.run_job(debug=debug)
            # Else if job is run then just check it
            elif wk.state == 'running' and wk.run:
                wk.check_job(debug=debug)

        # Trigger transactions - completed, not triggered
        workitems_to_trigger = self.env['work.workflow.workitem'].search([
            ('state', '=', 'done'),
            ('triggered', '=', False),
        ])
        for wk in workitems_to_trigger:
            wk.run_transitions(debug=debug)

        # Close completed instances
        running_instances = self.env['work.workflow.instance'].search([
            ('state', 'not in', ['done', 'canceled'])
        ])
        for inst in running_instances:
            if len(inst.workitem_ids.filtered(lambda x: x.state != 'done')) == 0:
                inst.state = 'done'
