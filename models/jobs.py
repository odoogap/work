# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools
from odoo.exceptions import ValidationError
import os
import time
import logging
import jenkins


_logger = logging.getLogger(__name__)


class WorkflowJobRouter(models.Model):
    _name = 'work.workflow.job.router'
    _inherit = 'work.workflow.job'

    @staticmethod
    def get_properties_defaults():
        return '{}'

    @api.model
    def run_job(self, values):
        item = super(WorkflowJobRouter, self).run_job(values)

        _logger.info('--- router job is running')
        item.update({'run': True})

        return item

    @api.model
    def check_job(self, values):
        item = super(WorkflowJobRouter, self).check_job(values)

        _logger.info('--- router job is done')
        item.update({'state': 'done'})

        return item


class WorkflowJobJenkins(models.Model):
    _name = 'work.workflow.job.jenkins'
    _inherit = 'work.workflow.job'

    @staticmethod
    def get_properties_defaults():
        return '{"job_name": "job_name"}'

    def get_vars(self):
        params = self.env['ir.config_parameter']
        jenkins_url = params.sudo().get_param('jenkins_ci.url', default='')
        jenkins_user = params.sudo().get_param('jenkins_ci.user', default='')
        jenkins_password = params.sudo().get_param('jenkins_ci.password', default='')
        return jenkins_url, jenkins_user, jenkins_password

    def jenkins_build_job(self, job):
        jenkins_url, jenkins_user, jenkins_password = self.get_vars()
        server = jenkins.Jenkins(jenkins_url, username=jenkins_user, password=jenkins_password)
        server.build_job(job)
        last_build_number = server.get_job_info(job)['lastCompletedBuild']['number']
        return {'last_build_number': last_build_number}

    def get_build_info(self, job, last_build_number):
        jenkins_url, jenkins_user, jenkins_password = self.get_vars()
        server = jenkins.Jenkins(jenkins_url, username=jenkins_user, password=jenkins_password)
        return server.get_build_info(job, last_build_number)

    @api.model
    def run_job(self, values):
        item = super(WorkflowJobJenkins, self).run_job(values)
        job_metadata = item.get('job_metadata').get('this_job')
        job_name = job_metadata.get('job_name', False)
        if job_name:
            res = self.jenkins_build_job(job_name)
            item.update({'run': True})
            item['job_metadata']['this_job'].update(res)
        else:
            raise ValidationError('Jenkins action error')
        return item

    @api.model
    def check_job(self, values):
        item = super(WorkflowJobJenkins, self).check_job(values)
        job_metadata = item.get('job_metadata').get('this_job')
        job_name = job_metadata.get('job_name', False)

        last_build_number = job_metadata.get('last_build_number', False)
        if last_build_number:
            res = self.get_build_info(job_name, last_build_number)
            if res['result'] == 'SUCCESS':
                item.update({'state': 'done'})

        return item


class WorkflowJobDraft(models.Model):
    """Purpose of this Draft job, is to be replaced by an
    implementation in a previous stage
    """
    _name = 'work.workflow.job.draft'
    _inherit = 'work.workflow.job'

    @staticmethod
    def get_properties_defaults():
        return '{}'

    @api.model
    def run_job(self, values):
        item = super(WorkflowJobRouter, self).run_job(values)

        _logger.info('--- draft job is running')
        item.update({'run': True})

        return item

    @api.model
    def check_job(self, values):
        item = super(WorkflowJobRouter, self).check_job(values)

        _logger.info('--- draft job is done')
        values.update({'state': 'done'})

        return item


class WorkflowProcess(models.Model):
    _inherit = "work.workflow.action"

    job_type = fields.Selection(
        selection_add=[
            ('work.workflow.job.jenkins', 'Jenkins Job'),
            ('work.workflow.job.draft', 'Draft Job')
        ])
