# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools
from odoo.exceptions import ValidationError

from exceptions import TypeError
from dateutil.relativedelta import relativedelta
import json
import logging


_logger = logging.getLogger(__name__)

WORK_INTERVAL_UNITS = [
    ('minutes', 'Minute(s)'),
    ('hours', 'Hour(s)'),
    ('days', 'Day(s)'),
    ('months', 'Month(s)'),
    ('years', 'Year(s)'),
]

WORK_INTERVALS = {
    'minutes': lambda interval: relativedelta(minutes=interval),
    'hours': lambda interval: relativedelta(hours=interval),
    'days': lambda interval: relativedelta(days=interval),
    'months': lambda interval: relativedelta(months=interval),
    'years': lambda interval: relativedelta(years=interval),
}


class WorkflowJob(models.AbstractModel):
    """ A mixin for models that implements workflow job
    """
    _name = "work.workflow.job"

    @staticmethod
    def get_properties_defaults():
        """

        :return: string default = "{}"
        """
        raise NotImplementedError("Should have implemented this")

    @api.model
    def run_job(self, values):
        """ Extend this method to add run action. First,
        Always check if *run* is False and *state* is running else don't run since check_job() will take care

        :param dict values: workitem new values:
                        * pid - process id, in case of need to check sys process
                        * state - workitem state
                        * run - flag indicating that process was triggered

        :return: dict with of the process if there is one and other vars
        """
        raise NotImplementedError("Should have implemented this")

    @api.model
    def check_job(self, values):
        """ Extend this method to add check step.
              * Run the job if its time for that. scheduled_run > now
              * Do whatever you need to check new state
                    values.update({'state': 'done'})
                    or just raise an exception
              * update the field job_output on each run

        :return: dict with full workitem record.
                 update changes to job_output
        """
        raise NotImplementedError("Should have implemented this")


class Workflow(models.Model):
    _name = 'work.workflow'
    _description = "Workflow Object"

    name = fields.Char(string='Reference', required=True, copy=False, index=True,
                       default=lambda x: _('New Workflow'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Published'),
        ('old', 'Deprecated'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')
    action_ids = fields.One2many('work.workflow.action', 'workflow_id', 'Actions')
    workitem_ids = fields.One2many('work.workflow.workitem', 'workflow_id', 'Workitems')
    workitem_ids_count = fields.Integer(compute='_workitem_ids_count')
    instance_ids = fields.One2many('work.workflow.instance', 'workflow_id', 'Instances')
    instance_ids_count = fields.Integer(compute='_instance_ids_count')
    start_metadata = fields.Text('Job Metadata', copy=True, default="{}")

    @api.multi
    @api.depends('workitem_ids')
    def _workitem_ids_count(self):
        for wkf in self:
            wkf.workitem_ids_count = len(filter(lambda x: x.state != 'done', wkf.workitem_ids))

    @api.multi
    @api.depends('instance_ids')
    def _instance_ids_count(self):
        for wkf in self:
            wkf.instance_ids_count = len(filter(lambda x: x.state != 'done', wkf.instance_ids))

    @api.multi
    def state_draft_set(self):
        return self.write({'state': 'draft'})

    @api.multi
    def state_sent_set(self):
        return self.write({'state': 'sent'})

    @api.multi
    def state_old_set(self):
        return self.write({'state': 'old'})

    @api.multi
    def run_workflow(self, values_json, debug=False, runner_host=False):
        """This method will be the starting method for the workflow

        :param values: Starting context where the workflow will run
        :param debug: To run the workflow in debug mode
        :param runner_host: This arg allow to define where the workflow will start
        :return:
        """

        try:
            values = json.loads(values_json)
        except TypeError:
            raise ValidationError(_("Input parameters are wrong."))

        for wkf in self:
            start_action = self.env['work.workflow.action'].search([('start', '=', True), ('workflow_id', '=', self.id)])
            if len(start_action) != 1:
                raise ValidationError(_("You need to have one start action to run."))
            if wkf.state != 'sent':
                raise ValidationError(_("This workflow is not in published state.\n"
                                        "You need to publish before running. "))
            instance_id = self.env['work.workflow.instance'].create({
                'workflow_id': self.id
            })
            values.update({'instance_id': instance_id.id})
            start_action.run_start(json.dumps(values), debug, runner_host=False)

    @api.multi
    def get_instances(self):
        tree_id = self.env.ref('work.work_workflow_instance_tree').id
        form_id = self.env.ref('work.work_workflow_instance_form').id
        search_id = self.env.ref('work.work_workflow_instance_search').id
        for wk in self:
            return {
                'name': 'Workflow Instance for %s' % wk.name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'work.workflow.instance',
                'domain': [('workflow_id', '=', wk.id)],
                'search_view_id': search_id,
                'views': [[tree_id, 'tree'], [form_id, 'form']],
            }

    @api.multi
    def get_workitems(self):
        for wk in self:
            tree_id = self.env.ref('work.work_workflow_workitem_tree').id
            form_id = self.env.ref('work.work_workflow_workitem_form').id
            search_id = self.env.ref('work.work_workflow_workitem_search').id
            return {
                'name': 'Workitems for %s' % wk.name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'work.workflow.workitem',
                'domain': [('workflow_id', '=', wk.id)],
                'search_view_id': search_id,
                'views': [[tree_id, 'tree'], [form_id, 'form']],
            }


class WorkflowAction(models.Model):
    _name = "work.workflow.action"
    _order = "name"
    _description = "Workflow Actions"

    name = fields.Char('Name', required=True)
    properties = fields.Text('Action Properties', required=False, default='{}')
    workflow_id = fields.Many2one('work.workflow', 'Workflow', required=True, ondelete='cascade', index=True)
    start = fields.Boolean('Start', help="This action is launched when the workflow starts.", index=True)
    job_type = fields.Selection(selection=[('work.workflow.job.router', 'Router')], string='Job', required=True)
    to_ids = fields.One2many('work.workflow.transition', 'action_from_id', 'Next Action')
    from_ids = fields.One2many('work.workflow.transition', 'action_to_id', 'Previous Actions')
    timeout = fields.Integer('Default Timeout(s)', help='Default timeout in seconds if 0 then there is no timeout', default=0)
    state = fields.Selection([
        ('draft', 'New'),
        ('active', 'Active'),
        ('disabled', 'Disabled')
        ], 'Status', copy=False, default="draft")

    @api.model
    def default_get(self, fields):
        result = super(WorkflowAction, self).default_get(fields)
        if 'job_type' in result:
            result['properties'] = self.env[result].get_properties_defaults()
        return result

    @api.onchange('job_type')
    def _onchange_job_type(self):
        if self.job_type:
            if not self.properties or self.properties=='':
                self.properties = self.env[self.job_type].get_properties_defaults()

    @api.multi
    @api.constrains('start')
    def _check_is_start(self):
        for act in self:
            if act.start and not len(act.from_ids) == 0:
                raise ValidationError(_(
                    "This activity cannot be start since has arriving transitions."))
            if act.start and act.job_type != 'work.workflow.job.router':
                raise ValidationError(_(
                    "Activity cannot be start unless is type router"))

    @api.model
    def run_start(self, values_json, debug=False, runner_host=False):
        """ Where it all starts
        """
        try:
            parsed_values = json.loads(values_json)
        except TypeError:
            raise ValidationError(_("Input parameters are wrong."))

        instance_id = parsed_values.get('instance_id', False)
        if not instance_id:
            raise ValidationError(_("Cannot start workflow without an instance id."))

        _logger.info('WKF: Action %s is starting' % self.name)
        self.env['work.workflow.workitem'].create({
            'action_id': self.id,
            'state': 'draft',
            'runner_host': runner_host,
            'instance_id': instance_id,
            'job_metadata': json.dumps(parsed_values)
        }, debug=debug)


class WorkflowTransition(models.Model):
    _name = "work.workflow.transition"
    _description = "Workflow Transition"

    name = fields.Char(compute='_compute_name', string='Name')
    action_from_id = fields.Many2one('work.workflow.action', 'Previous Action', index=1, required=True, ondelete="cascade")
    action_to_id = fields.Many2one('work.workflow.action', 'Next Action', required=True, ondelete="cascade")
    condition_name = fields.Char('Condition Name', required=True, default='Condition')
    condition = fields.Text('Condition', required=True, default="True",
                            help="Python expression to decide whether the activity can be executed, otherwise it"
                                 " will be deleted or cancelled."
                                 "The expression may use the following [browsable] variables:\n"
                                 "   - metadata: the job metadata\n"
                                 "   - workitem: the campaign workitem\n")
    interval_nbr = fields.Integer('Interval Value', required=True, default=1)
    interval_type = fields.Selection(WORK_INTERVAL_UNITS, 'Interval Unit', required=True, default='days')
    trigger = fields.Selection([
        ('auto', 'Automatic'),
        ('time', 'Time and Condition'),
        ], 'Trigger', required=True, default='auto',
        help="How is the destination workitem triggered")

    _sql_constraints = [
        ('interval_positive', 'CHECK(interval_nbr >= 0)', 'The interval must be positive or zero')
    ]

    def _compute_name(self):
        # name formatters that depend on trigger
        formatters = {
            'auto': _('Automatic transition'),
            'time': _('After %(interval_nbr)d %(interval_type)s if %(condition_name)s'),
        }
        # get the translations of the values of selection field 'interval_type'
        model_fields = self.fields_get(['interval_type'])
        interval_type_selection = dict(model_fields['interval_type']['selection'])

        for transition in self:
            values = {
                'interval_nbr': transition.interval_nbr,
                'interval_type': interval_type_selection.get(transition.interval_type, ''),
                'condition_name': transition.condition_name or ''
            }
            transition.name = formatters[transition.trigger] % values
