from django.db.models import Count, EmailField, ExpressionWrapper, \
    F, Func, Value

from prometheus_client.core import GaugeMetricFamily

from researcher_workspace import models as researcher_workspace_models
from researcher_workspace import settings
from vm_manager import models as vm_manager_models


class BumblebeeMetricsCollector(object):
    def collect(self):
        volumes = vm_manager_models.Volume.objects.all()
        all_users = researcher_workspace_models.User.objects.all()
        exclusions = [u.get_username() for u in all_users if u.is_superuser] \
            + settings.EXCLUDE_FROM_USAGE
        for dimension in ['created', 'running', 'shelved']:

            name = f"bumblebee_desktops_{dimension}"
            desc = f"Number of {dimension} desktops"
            if dimension == 'created':
                qs = volumes
            elif dimension == 'running':
                qs = volumes.filter(deleted=None, shelved_at=None)
            elif dimension == 'shelved':
                qs = volumes.filter(deleted=None).exclude(shelved_at=None)

            # filter out super-user and monitoring desktops
            qs = qs.exclude(user__username__in=exclusions)

            # bumblebee_desktops_*_total
            yield GaugeMetricFamily(f"{name}_total", desc,
                                    value=qs.count() if qs else 0)

            # bumblebee_desktops_*_by_type
            g = GaugeMetricFamily(
                f"{name}_by_type", f"{desc} by_type", labels=['type'])
            new_qs = qs.values('operating_system') \
                       .annotate(Count('operating_system'))
            for t in new_qs:
                g.add_metric([t['operating_system']],
                             t['operating_system__count'])
            yield g

            # bumblebee_desktops_*_by_zone
            g = GaugeMetricFamily(
                f"{name}_by_zone", f"{desc} by_zone", labels=['zone'])
            new_qs = qs.values('zone').annotate(Count('zone'))
            for t in new_qs:
                g.add_metric([t['zone']], t['zone__count'])
            yield g

            # bumblebee_desktops_*_by_domain
            g = GaugeMetricFamily(
                f"{name}_by_domain", f"{desc} by domain", labels=['domain'])
            new_qs = qs.values(
                domain=ExpressionWrapper(
                    Func(F('user__email'), Value('@'),
                         Value(-1), function='substring_index'),
                    output_field=EmailField())).annotate(Count('domain'))
            for t in new_qs:
                g.add_metric([t['domain']], t['domain__count'])
            yield g
