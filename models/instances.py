# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

from . workflow import WORK_INTERVAL_UNITS, WORK_INTERVALS

from datetime import datetime
import logging
import sys
import json

_logger = logging.getLogger(__name__)


class WorkflowInstance(models.Model):
    _name = "work.workflow.instance"
    _description = "Workflow instance"

    name = fields.Char(compute='_compute_name', string='Name')
    workflow_id = fields.Many2one('work.workflow', readonly=True, store=True, copy=False, required=True, ondelete="set null")
    workitem_ids = fields.One2many('work.workflow.workitem', 'instance_id', 'Workitems', ondelete="set null")
    state = fields.Selection([
        ('running', 'Running'),
        ('done', 'Done'),
        ], 'Status', required=True, default='running',
        help="Status of the workflow instance")

    def _compute_name(self):
        for inst in self:
            inst.name = '%(create_date)s - %(name)s - INST%(id)s' %\
                        {'name': inst.workflow_id.name, 'id': inst.id, 'create_date': inst.create_date}

    @api.multi
    def get_workitems(self):
        tree_id = self.env.ref('work.work_workflow_instance_tree').id
        form_id = self.env.ref('work.work_workflow_instance_form').id
        search_id = self.env.ref('work.work_workflow_instance_search').id
        for wk in self:
            return {
                'name': 'Workitems for %s' % wk.workflow_id.name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'work.workflow.workitem',
                'domain': [('workflow_id', '=', wk.workflow_id.id)],
                'search_view_id': search_id,
                'views': [[tree_id, 'tree'], [form_id, 'form']],
                'target': 'main'
            }


class WorkflowWorkitem(models.Model):
    _name = "work.workflow.workitem"
    _description = "Workflow Workitem"

    name = fields.Char(compute='_compute_name', string='Name')
    runner_host = fields.Char(string='Host', default=False)
    action_id = fields.Many2one('work.workflow.action', 'Action', required=True, readonly=True, ondelete="set null")
    job_type = fields.Selection(related='action_id.job_type')
    workflow_id = fields.Many2one('work.workflow', related='instance_id.workflow_id', readonly=True,
                                  copy=True, ondelete="set null", store=True)
    interval_nbr = fields.Integer('Interval Value', required=True, default=1, copy=False)
    interval_type = fields.Selection(WORK_INTERVAL_UNITS, 'Interval Unit', required=True, default='minutes', copy=False)
    trigger = fields.Selection([
        ('auto', 'Automatic'),
        ('time', 'Time'),
        ], 'Trigger', required=True, default='auto',
        help="How is the destination workitem triggered")

    instance_id = fields.Many2one('work.workflow.instance', string="Workflow Instance", copy=True,
                                  required=True, ondelete="set null")
    completed_ids = fields.Many2many('work.workflow.transition', 'completed_transitions_rel', 'transition_id',
                                     'workitem_id',
                                     string='Completed Transitions', copy=False, ondelete="cascade")
    # Job values
    scheduled_run = fields.Datetime('Scheduled Run', compute='_compute_scheduled_run', store=True, copy=False)
    job_metadata = fields.Text('Job Metadata', copy=True, default="{}")
    run = fields.Boolean('Process was started', default=False, copy=False)
    triggered = fields.Boolean('Transitions triggered?', default=False, copy=False)
    timeout = fields.Boolean('Process has Timed Out?', default=False, copy=False)
    pid = fields.Integer('Process ID', copy=False, default=0)
    state = fields.Selection([
        ('todo', 'To Do'),
        ('running', 'Running'),
        ('cancelled', 'Cancelled'),
        ('exception', 'Exception'),
        ('done', 'Done'),
        ], 'Status', readonly=True, copy=False, default='todo')
    error_msg = fields.Text('Error Message', readonly=True, copy=False, default='')

    @api.model
    def create(self, values, debug=False):
        """While creating the workitem on the database we will send all current
        field values and at the end we will just update: job_output, pid, run and state
        This routine will only create the work-item, not run it

        :param dict values: only with the fields [ 'job_output', 'pid', 'run', 'state']
        :param debug: debug flag that will allow to see the stack trace
        :return:
        """
        # Get the defaults and calculate scheduled_run datetime
        defaults = self.default_get(['trigger', 'interval_type', 'interval_nbr', 'job_type', 'state'])
        defaults.update(values)
        values = defaults
        create_date = datetime.now()
        trigger = values.get('trigger')
        interval_type = values.get('interval_type')
        interval_nbr = values.get('interval_nbr')
        job_metadata = json.loads(values.get('job_metadata'))

        if trigger == 'time':
            scheduled_run = create_date + WORK_INTERVALS[interval_type](interval_nbr)
        else:
            scheduled_run = create_date

        # Don't need to do this , but just in case i decide to use store≃True in future
        values.update({'scheduled_run': scheduled_run.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})

        # Decide the state depending on the trigger conditions
        if scheduled_run >= create_date:
            values.update({'state': 'running'})

        action_id = values.get('action_id')

        if not action_id:
            raise ValidationError('Workitem must contain an action_id')
        else:
            action = self.env['work.workflow.action'].browse(action_id)
            properties = safe_eval(action.properties, job_metadata)
            job_metadata.update({'this_job': properties})
            values.update({
                'job_metadata': json.dumps(job_metadata)
            })

        return super(WorkflowWorkitem, self).create(values)

    @api.model
    def run_job(self, debug):
        for item in self:
            values = item.read()[0]
            job_metadata_json = values.get('job_metadata', '{}')

            # Check if job metadata can be parsed as json
            try:
                job_metadata = json.loads(job_metadata_json)
            except TypeError:
                raise ValidationError(_("Input parameters are wrong. %s"))

            # Job values for explicitly
            job_values = {
                'job_metadata': job_metadata,
                'scheduled_run': item.scheduled_run,
                'run': item.run,
                'triggered': item.run,
                'timeout': item.run,
                'pid': item.run,
                'state': item.run,
                'error_msg': item.error_msg
            }

            values = self._run_job(job_values, item.job_type, debug)

            item.job_metadata = json.dumps(values.get('job_metadata', '{}'))
            item.scheduled_run = values.get('scheduled_run', item.create_date)
            item.run = values.get('run', False)
            item.triggered = values.get('triggered', False)
            item.timeout = values.get('timeout', 0)
            item.pid = values.get('pid', 0)
            item.state = values.get('state', 'todo')
            item.error_msg = values.get('error_msg', '')

    def _run_job(self, values, job_type, debug=False):
        now = datetime.now()

        scheduled_run = values['scheduled_run']

        if job_type.startswith('work.workflow.job.'):
            res = {}
            scheduled_run = datetime.strptime(scheduled_run, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            if scheduled_run >= now:
                # Debug for development mode
                if debug:
                    values = self.env[job_type].run_job(values)
                else:
                    try:
                        values = self.env[job_type].run_job(values)
                    except:
                        e = sys.exc_info()[0]
                        values['error_msg'] = e
                values['job_metadata'] = json.dumps(values.get('job_metadata', ''))
        return values

    @api.model
    def check_job(self, debug=False):
        for item in self:
            values = item.read()[0]
            values.update({
                'job_metadata': safe_eval(unicode(json.loads(values.get('job_metadata', '{}'))))
            })
            job_type = item.job_type
            if job_type.startswith('work.workflow.job.'):
                res = {}
                # Debug for development mode
                if debug:
                    res = item.env[job_type].check_job(values)
                else:
                    try:
                        res = item.env[job_type].check_job(values)
                    except:
                        e = sys.exc_info()[0]
                        item.error_msg = e

            item.job_metadata = json.dumps(values.get('job_metadata', ''))
            if 'state' in res:
                item.state = res['state']
        return True

    def _compute_name(self):
        for item in self:
            if item.job_type:
                item.name = '%(instance)s - %(job_type)s - %(name)s - %(id)s' %\
                            {'name': item.action_id.name, 'id': item.id, 'job_type': item.job_type.split('.')[-1],
                             'instance': item.instance_id.name}
            else:
                item.name = 'NA'

    @api.one
    @api.depends('create_date', 'interval_type', 'interval_nbr')
    def _compute_scheduled_run(self):
        if self.trigger == 'time':
            self.scheduled_run = datetime.strptime(self.create_date, tools.DEFAULT_SERVER_DATETIME_FORMAT) + WORK_INTERVALS[
                self.interval_type](self.interval_nbr)
        else:
            self.scheduled_run = self.create_date

    @api.model
    def run_transitions(self, debug=False):
        job_id = self.id
        _logger.info("---- run transitions job_id %d", job_id)
        transitions_not_done = self.action_id.to_ids.filtered(lambda x: x.id not in self.completed_ids.ids)
        if len(transitions_not_done) == 0:
            self.triggered = True
        else:
            for transition in transitions_not_done:
                condition = transition.condition

                eval_context = {
                    'metadata': safe_eval(unicode(json.loads(self.job_metadata))),
                    'workitem': self,
                }
                if safe_eval(condition, eval_context):
                    new_wk_item = self.copy({
                        'action_id': transition.action_to_id.id,
                        'trigger': transition.trigger,
                        'interval_nbr': transition.interval_nbr,
                        'interval_type': transition.interval_type,
                        'job_type': transition.action_to_id.job_type,
                        'triggered': False,
                        'run': False,
                    })

            # Mark all transitions as completed
            self.completed_ids = [(6, 0,  transitions_not_done.ids)]
