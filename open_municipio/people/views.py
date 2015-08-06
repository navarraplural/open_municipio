from datetime import datetime, date
import logging

from django.shortcuts import get_object_or_404

from django.conf import settings
from django.contrib.sites.models import Site
from django.db.models import Q, Count
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.views.generic import TemplateView, DetailView, ListView, RedirectView
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage

from open_municipio.people.models import Institution, InstitutionCharge, Person, municipality, InstitutionResponsability, Group
from open_municipio.monitoring.forms import MonitoringForm
from open_municipio.acts.models import Act, CGDeliberation, Deliberation, Interrogation, Interpellation, Motion, Agenda, Amendment, ActSupport
from open_municipio.acts.models import Speech
from open_municipio.events.models import Event
from open_municipio.acts.models import Speech
from open_municipio.people.models import Sitting, SittingItem

from open_municipio.om_search.forms import RangeFacetedSearchForm
from open_municipio.om_search.mixins import FacetRangeDateIntervalsMixin
from open_municipio.om_search.views import ExtendedFacetedSearchView

from django.core import serializers
from haystack.query import SearchQuerySet
from haystack.inputs import Raw

from sorl.thumbnail import get_thumbnail

logger = logging.getLogger('webapp')

class InstitutionListView(ListView):
    model = Institution
    template_name = 'people/institution_list.html'
    
    
class MayorDetailView(RedirectView):
    def get_redirect_url(self, **kwargs):
        return municipality.mayor.as_charge.person.get_absolute_url()


class PoliticianSearchView(ListView):
    """
    Returns a JSON response of unique politicians (Person) having
    "key" in first_name or last_name.

    Used in typeahead in Home page
    """

    def get(self, request, *args, **kwargs):
        key = request.GET.get('key', '')
        ajax = request.GET.get('ajax', 0)
        max_rows = request.GET.get('max_rows', 10)

        current_site = Site.objects.get(pk=settings.SITE_ID)

        charges = InstitutionCharge.objects.\
            filter(Q(institution__institution_type=Institution.COUNCIL) | Q(institution__institution_type=Institution.CITY_GOVERNMENT)).\
            filter(Q(person__first_name__icontains=key) | Q(person__last_name__icontains=key))[0:max_rows]

        # build persons array,substituting the img with a 50x50 thumbnail
        # and returning the absolute url of the thumbnail
        persons = []
        for c in charges:
            if c.person not in persons:
                person = c.person
                try:
                    img = get_thumbnail("http://%s/media/%s" % (current_site, person.img), "50x50", crop="center", quality=99)
                    person.img = img.url
                except BaseException as e:
                    person.img = "http://%s/static/img/placehold/face_50.png#%s" % (current_site, e)

                persons.append(person)

        json_data = serializers.serialize('json', persons)
        return HttpResponse(json_data, mimetype='text/json')


class CouncilListView(TemplateView):
    """
    Renders the Council page
    """
    template_name = 'people/institution_council.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(CouncilListView, self).get_context_data(**kwargs)

        groups = municipality.council.groups.active().order_by("name")
        committees = municipality.committees.as_institution
        latest_acts = Act.objects.filter(
            emitting_institution__institution_type=Institution.COUNCIL
            ).order_by('-presentation_date')[:3]
        events = Event.objects.filter(institution__institution_type=Institution.COUNCIL)
        num_acts = dict()
        act_types = [
            Deliberation, Motion, Interrogation, Interpellation, Agenda, Amendment
            ]
        for act_type in act_types:
            num_acts[act_type.__name__.lower()] = act_type.objects.filter(
                emitting_institution__institution_type=Institution.COUNCIL
                ).count()
    
        members = SearchQuerySet()\
            .filter(django_ct = 'people.institutioncharge')\
            .filter(institution = _("Counselor"))\
            .filter(is_active = _("yes"))

        extra_context = {
            'members': members,
            'groups': groups,
            'committees': committees,
            'latest_acts': latest_acts,
            'num_acts': num_acts,
            'events': events,
            }
        
        # Update context with extra values we need
        context.update(extra_context)
        
        return context


class CityGovernmentView(TemplateView):
    """
    Renders the City Government page
    """
    template_name = 'people/institution_citygov.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(CityGovernmentView, self).get_context_data(**kwargs)

        latest_acts = Act.objects.filter(
            emitting_institution__institution_type=Institution.CITY_GOVERNMENT
            ).order_by('-presentation_date')[:3]
        events = Event.objects.filter(institution__institution_type=Institution.CITY_GOVERNMENT)
        num_acts = dict()
        act_types = [
            Deliberation, Motion, Interrogation, Interpellation, Agenda, Amendment
            ]
        for act_type in act_types:
            num_acts[act_type.__name__.lower()] = act_type.objects.filter(
                emitting_institution__institution_type=Institution.CITY_GOVERNMENT
                ).count()
    
        members = SearchQuerySet()\
            .filter(django_ct = 'people.institutioncharge')\
            .filter(Q(institution__exact = _("City Government Member")) | Q(institution = _("Mayor")))\
            .filter(is_active = _("yes"))

        extra_context = {
            'latest_acts': latest_acts,
            'num_acts': num_acts,
            'events': events,
            'members': members,
            }

        # Update context with extra values we need
        context.update(extra_context)
        return context


class GroupListView(ListView):
    model = Group
    template_name = 'people/institution_groups.html'
    context_object_name = 'groups'

    def get_queryset(self):
        return Group.objects.active().order_by("name")

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        extra_context = super(GroupListView, self).get_context_data(**kwargs)
        return extra_context


class GroupDetailView(DetailView):
    model = Group
    template_name = 'people/institution_group.html'
    context_object_name = "group"

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        extra_context = super(GroupDetailView, self).get_context_data(**kwargs)

        extra_context['groups'] = municipality.council.groups.filter(groupcharge__end_date__isnull=True).distinct()
    
        members = SearchQuerySet()\
            .filter(django_ct = 'people.institutioncharge')\
            .filter(institution = _("Counselor"))\
            .filter(is_active = _("yes"))\
            .filter(current_group = self.object.slug)

        extra_context['members'] = members

        return extra_context


class CommitteeListView(ListView):
    model = Institution
    template_name = 'people/institution_committees.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        extra_context = super(CommitteeListView, self).get_context_data(**kwargs)


        extra_context['committees'] = municipality.committees.as_institution()
        extra_context['events'] = Event.objects.filter(institution__in=municipality.committees.as_institution())

        return extra_context

class CommitteeDetailView(DetailView):
    """
    Renders the Committee page
    """
    model = Institution
    template_name = 'people/institution_committee.html'
    context_object_name = "committee"

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(CommitteeDetailView, self).get_context_data(**kwargs)

        # Are we given a real Committee institution as input? If no,
        # raise 404 exception.
        if self.object.institution_type != Institution.COMMITTEE:
            raise Http404

        committee_list = municipality.committees.as_institution()

        # fetch charges and add group
        president = self.object.president
        if president and president.charge.original_charge_id:
            president.group = InstitutionCharge.objects.current().select_related().\
                                  get(pk=president.charge.original_charge_id).council_group
        vicepresidents = self.object.vicepresidents
        for vp in vicepresidents:
            if vp and vp.charge.original_charge_id:
                vp.group = InstitutionCharge.objects.current().select_related().\
                    get(pk=vp.charge.original_charge_id).council_group

        members = self.object.members.order_by('person__last_name')
        current_i_charges = InstitutionCharge.objects.current().select_related()
        for m in members:
            m_as_counselor = current_i_charges.filter(pk=m.original_charge_id)
            if len(m_as_counselor) == 1:
                m_as_counselor = m_as_counselor[0]
                m.group = m_as_counselor.council_group
            else:
                m.group = None



        resources = dict(
            (r['resource_type'], {'value': r['value'], 'description': r['description']})
                for r in self.object.resources.values('resource_type', 'value', 'description')
        )


        events = Event.objects.filter(institution=self.object)

        extra_context = {
            'committees': committee_list,
            'members': members,
            'president': president,
            'resources': resources,
            'vice_presidents': vicepresidents,
            'events': events,
        }

        # Update context with extra values we need
        context.update(extra_context)
        return context


class PoliticianDetailView(DetailView):
    model = Person
    context_object_name = 'person'
    template_name='people/politician_detail.html'

    def get_charge(self):

        institution_slug = self.kwargs.get("institution_slug", None)
        year = int(self.kwargs.get("year", "0"))
        month = int(self.kwargs.get("month", "0"))
        day = int(self.kwargs.get("day", "0"))

        charge = None

        if institution_slug and year and month and day: 
            start_date = date(year=year, month=month, day=day)
            charge = InstitutionCharge.objects.exclude(institution__institution_type=Institution.COMMITTEE).get(person=self.object, institution__slug=institution_slug, start_date=start_date)
        else:
            all_charges = self.object.all_institution_charges.exclude(institution__institution_type=Institution.COMMITTEE).order_by("-start_date")
            if len(all_charges) > 0:
                charge = all_charges[0]

        print "current charge: %s (%s - %s)" % (charge, charge.start_date, charge.end_date)

        return charge

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(PoliticianDetailView, self).get_context_data(**kwargs)
        # Add in a QuerySet of all the institutions
        context['institution_list'] = Institution.objects.all()

        context['resources'] = { }

        person = self.object

        context['person'] = person

        charge = self.get_charge()

        context['charge'] = charge

        for r in person.resources.values('resource_type', 'value', 'description'):
            context['resources'].setdefault(r['resource_type'], []).append(
                {'value': r['value'], 'description': r['description']}
            )


        past_charges = person.get_past_institution_charges()
        context['past_charges'] = past_charges

        current_charges = person.get_current_institution_charges().exclude(
            institutionresponsability__charge_type__in=(
                InstitutionResponsability.CHARGE_TYPES.mayor,
            ),
            institutionresponsability__end_date__isnull=True
        )
        context['current_charges'] = current_charges
        context['current_institutions'] = current_charges.values("institution__name").distinct()
        context['current_committee_charges'] = person.get_current_committee_charges()
#        context['is_counselor'] = person.is_counselor()
#        context['current_counselor_charge'] = person.current_counselor_charge()

        context['current_groupcharge'] = person.current_groupcharge

        if charge:
            historical_groupcharges = charge.historical_groupcharges #person.historical_groupcharges
            context['historical_groupcharges'] = historical_groupcharges.order_by('start_date') if historical_groupcharges else None

        # Is the current charge a counselor? If so, we show present/absent
        # graph
        if charge and charge.is_counselor:
            # Calculate average present/absent for counselors
            percentage_present = 0
            percentage_absent = 0
            n_counselors = len(municipality.council.charges)
            for counselor in municipality.council.charges:
                n_votations = counselor.n_present_votations \
                    + counselor.n_absent_votations
                if n_votations > 0:
                    percentage_present += \
                        float(counselor.n_present_votations) / n_votations
                    percentage_absent += \
                        float(counselor.n_absent_votations) / n_votations
            # Empty city council? That can't be the case!
            # n_counselors is supposed to be > 0
            context['percentage_present_votations_average'] = \
                "%.1f" % (float(percentage_present) / n_counselors * 100)
            context['percentage_absent_votations_average'] = \
                "%.1f" % (float(percentage_absent) / n_counselors * 100)

            # Calculate present/absent for current counselor
#            charge = context['current_counselor_charge']
            charge.percentage_present_votations = charge.percentage_absent_votations = 0.0

            if charge.n_present_votations + charge.n_absent_votations > 0:
                context['n_total_votations'] = charge.n_present_votations + charge.n_absent_votations
                context['percentage_present_votations'] = \
                    "%.1f" % (float(charge.n_present_votations) /\
                              context['n_total_votations'] * 100.00)
                context['percentage_absent_votations'] = \
                    "%.1f" % (float(charge.n_absent_votations) /\
                              context['n_total_votations'] * 100.00)

            if charge.n_present_votations > 0:
                context['percentage_rebel_votations'] = "%.1f" % (float(100 * charge.n_rebel_votations / charge.n_present_votations))

        # Current politician's charge votes for key votations
        # last 10 are passed to template
#        charge = context['current_counselor_charge']
        if charge and charge.is_counselor:
            context['current_charge_votes'] = charge.chargevote_set \
                .filter(votation__is_key=True) \
                .order_by('-votation__sitting__date')[0:10]

        # last 10 presented acts

#        presented_acts = Act.objects\
#            .filter(actsupport__charge__pk__in=person.current_institution_charges)\
#            .order_by('-presentation_date')
        presented_acts = Act.objects\
            .filter(actsupport__charge=charge)\
            .order_by('-presentation_date')
        context['n_presented_acts'] = presented_acts.count()
        context['presented_acts'] = presented_acts[0:10]

        # last 5 speeches
        speeches = Speech.objects\
            .filter(author=person)
        context['n_speeches'] = speeches.count()
        context['speeches'] = speeches[0:5]

        # is the user monitoring the act?
        context['is_user_monitoring'] = False
        try:
            if self.request.user.is_authenticated():
                # add a monitoring form, to context,
                # to switch monitoring on and off
                context['monitoring_form'] = MonitoringForm(data = {
                    'content_type_id': person.content_type_id,
                    'object_pk': person.id,
                    'user_id': self.request.user.id
                })

                if person in self.request.user.get_profile().monitored_objects:
                    context['is_user_monitoring'] = True
        except ObjectDoesNotExist:
            context['is_user_monitoring'] = False

        context['person_topics'] = []


        #
        # extract all the topics of the acts presented by the person in the view
        #

        # get the person from the view
        p = person #self.object

        for charge in p.all_institution_charges:
    
            for act in charge.presented_acts:
                for topic in act.topics:

                    # avoid repetitions, by skipping categories and tags already appended
                    if topic.category in [t.category for t in context['person_topics']]:
                        if topic.tag in [t.tag for t in context['person_topics']]:
                            continue

                    # append topic
                    context['person_topics'].append(topic)


        """
        # Obscurated form of the above code :-)

        for topics in [y.topics for x in person.get_current_institution_charges() for y in x.presented_act_set.all() ]:
            for topic in topics:
                if topic.category in [t.category for t in context['person_topics']]:
                    if topic.tag in [t.tag for t in context['person_topics']]:
                        continue
                context['person_topics'].append(topic)
        """

        return context


class PoliticianListView(TemplateView):
    """
    Renders the Politicians page
    """
    template_name = 'people/politician_list.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(PoliticianListView, self).get_context_data(**kwargs)

        # municipality access point to internal API
        context['municipality'] = municipality

        # exclude mayor from council members
        # fetch most or least
        counselors = context['counselors'] = municipality.council.charges.exclude(
            institutionresponsability__charge_type__in=(
                InstitutionResponsability.CHARGE_TYPES.mayor,
            ),
            institutionresponsability__end_date__isnull=True
        ).select_related().exclude(n_present_votations=0).order_by('person__last_name')

        # fetch most or least
        context['most_rebellious'] = counselors.extra(select={'perc_rebel':'(n_rebel_votations * 100.0) / GREATEST (n_absent_votations + n_present_votations,1)'}).order_by('-perc_rebel')[0:3]
        context['most_trustworthy'] = counselors.order_by('n_rebel_votations')[0:3]
        context['least_absent'] = counselors.extra(select={'perc_absences':'(n_absent_votations * 100.0) / GREATEST (n_absent_votations + n_present_votations,1)'}).order_by('perc_absences')[0:3]
        context['most_absent'] = counselors.order_by('-n_absent_votations')[0:3]
        context['most_speeches'] = counselors.annotate(_n_speeches=Count('person__speech')).order_by('-_n_speeches')[0:3]

        today = datetime.today()

        context['most_acts'] = counselors.\
                               filter(actsupport__support_type=ActSupport.SUPPORT_TYPE.first_signer).\
                               annotate(n_acts=Count('actsupport')).order_by('-n_acts')[0:3]

        context['most_interrogations'] = counselors.\
                                         filter(Q(actsupport__act__interrogation__isnull=False) |
                                                Q(actsupport__act__interpellation__isnull=False),
                                                Q(actsupport__support_type=ActSupport.SUPPORT_TYPE.first_signer)).\
                                         filter(start_date__lte=today).filter(Q(end_date=None) | Q(end_date__gte=today)).\
                                         annotate(n_acts=Count('actsupport')).order_by('-n_acts')[0:3]

        context['most_motions'] = counselors.\
                                         filter(Q(actsupport__act__motion__isnull=False) |
                                                Q(actsupport__act__agenda__isnull=False),
                                                Q(actsupport__support_type=ActSupport.SUPPORT_TYPE.first_signer)).\
                                         filter(start_date__lte=today).filter(Q(end_date=None) | Q(end_date__gte=today)).\
                                         annotate(n_acts=Count('actsupport')).order_by('-n_acts')[0:3]

        # take latest group charge changes
        """
        context['last_group_changes'] = [gc.charge for gc in GroupCharge.objects.filter(
            charge__in= [gc.charge.id for gc in GroupCharge.objects.filter(end_date__isnull=True)]
        ).filter(end_date__isnull=False).order_by('-end_date')[0:3]]
        """

        # statistics
        from django.utils.datastructures import SortedDict

        context['gender_stats'] = SortedDict()
        context['gender_stats']['Donne'] = 0
        context['gender_stats']['Uomini'] = 0

        context['age_stats'] = SortedDict()
        context['age_stats']['ventenni'] = 0
        context['age_stats']['trentenni'] = 0
        context['age_stats']['quarantenni'] = 0
        context['age_stats']['cinquantenni'] = 0
        context['age_stats']['sessantenni'] = 0
        context['age_stats']['seniores'] = 0

#        all_members = set(list(municipality.council.members) + list(municipality.gov.members) + [municipality.mayor.as_charge,])

        list_members = []
        
        if municipality.council:
            list_members.extend(municipality.council.members)

        if municipality.gov:
            list_members.extend(municipality.gov.members)

        if municipality.mayor and municipality.mayor.as_charge:
            list_members.append(municipality.mayor.as_charge)

        all_members = set(list_members)

        for charge in all_members:
            if charge.person.sex == Person.MALE_SEX:
                context['gender_stats']['Uomini'] += 1
            elif charge.person.sex == Person.FEMALE_SEX:
                context['gender_stats']['Donne'] += 1

            if charge.person.age <= 25:
                context['age_stats']['ventenni'] += 1
            if 25 < charge.person.age <= 35:
                context['age_stats']['trentenni'] += 1
            if 35 < charge.person.age <= 45:
                context['age_stats']['quarantenni'] += 1
            if 45 < charge.person.age <= 55:
                context['age_stats']['cinquantenni'] += 1
            if 55 < charge.person.age <= 65:
                context['age_stats']['sessantenni'] += 1
            if 65 < charge.person.age:
                context['age_stats']['seniores'] += 1

        context['gender_stats'] = context['gender_stats']
        context['age_stats'] = context['age_stats']

        # number of different acts
        num_acts = dict()
        act_types = [
            CGDeliberation, Deliberation, Motion, Interrogation, Interpellation, Agenda, Amendment
        ]
        for act_type in act_types:
#            num_acts[act_type.__name__.lower()] = act_type.objects.filter(
#                emitting_institution__institution_type=Institution.COUNCIL
#            ).count()
            num_acts[act_type.__name__.lower()] = act_type.objects.all().count()

        context['num_acts'] = num_acts

        return context

class SittingCalendarView(TemplateView):
    template_name = "people/sitting_calendar.html"

    def get_context_data(self, **kwargs):
        context = super(SittingCalendarView, self).get_context_data(**kwargs)

        sittings = Sitting.objects.filter(institution__institution_type=Institution.COUNCIL)
        events = Event.objects.filter(institution__institution_type=Institution.COUNCIL)

        extra_context = {
            'sittings'  : sittings,
            'events'    : events,
        }

        context.update(extra_context)
        return context

class SittingDetailView(DetailView):
    model = Sitting
    context_object_name = 'sitting'
    template_name = 'people/sitting_detail.html'

    def get_context_data(self, **kwargs):

        context = super(SittingDetailView, self).get_context_data(**kwargs)

        curr = context['sitting']

        events = Event.objects.filter(institution__institution_type=Institution.COUNCIL)

        sitting_items = curr.sitting_items.order_by("seq_order")

        extra = {
            "events"    : events,
            "sitting_items" : sitting_items,
        }

        context.update(extra)
        return context

class SittingItemDetailView(DetailView):
    model = SittingItem
    context_object_name = 'sitem'
    template_name = 'people/sittingitem_detail.html'

    def get_context_data(self, **kwargs):
        context = super(SittingItemDetailView, self).get_context_data(**kwargs)

        sitem = context['sitem']
        curr = sitem.sitting

        # get the speeches related to the sitting item
        speeches = Speech.objects.filter(sitting_item=sitem).order_by("seq_order","initial_time")

        # get the related acts
#        acts_pk = sitem.related_act_set #values("related_act_set").distinct()
#        acts = Act.objects.filter(pk__in=acts_pk)
        acts = sitem.related_act_set.all()

        extra = {
            "speeches":speeches,
            "acts":acts,
        }

        context.update(extra)
        return context


def show_mayor(request):
    return HttpResponseRedirect( municipality.mayor.as_charge.person.get_absolute_url() )

class ChargeSearchView(ExtendedFacetedSearchView, FacetRangeDateIntervalsMixin):
    """

    This view allows faceted search and navigation of the comments.

    It extends an extended version of the basic FacetedSearchView,
    and can be customized

    """
    __name__ = 'ChargeSearchView'

    FACETS_SORTED = [ 'start_date', 'end_date', 'is_active', 'institution', 'responsability' ]

    FACETS_LABELS = {
        'is_active': _('Active'),
        'start_date': _('Start date'),
        'end_date': _('End date'),
        'institution': _('Institution'),
        'responsability': _('Responsability')
    }
    DATE_INTERVALS_RANGES = { }

    def __init__(self, *args, **kwargs):

        # dynamically compute date ranges for faceted search
        curr_year = datetime.today().year
        for curr_year in xrange(settings.OM_START_YEAR, curr_year + 1):
            date_range = self._build_date_range(curr_year)
            self.DATE_INTERVALS_RANGES[curr_year] = date_range
    
        sqs = SearchQuerySet().filter(django_ct='people.institutioncharge')\
            .filter(institution = Raw("[* TO *]")).facet('is_active')\
            .facet('institution').facet('responsability')

        for (year, range) in self.DATE_INTERVALS_RANGES.items():
            sqs = sqs.query_facet('start_date', range['qrange'])

        for (year, range) in self.DATE_INTERVALS_RANGES.items():
            sqs = sqs.query_facet('end_date', range['qrange'])

        #kwargs['searchqueryset'] = sqs.order_by('-start_date').highlight()
        kwargs['searchqueryset'] = sqs.order_by('last_name').highlight()

        # Needed to switch out the default form class.
        if kwargs.get('form_class') is None:
            kwargs['form_class'] = RangeFacetedSearchForm

        super(ChargeSearchView, self).__init__(*args, **kwargs)

    def _build_date_range(self, curr_year):
        return { 'qrange': '[%s-01-01T00:00:00Z TO %s-12-31T00:00:00Z]' % \
                (curr_year, curr_year), 'r_label': curr_year }

    def build_page(self):
        self.results_per_page = int(self.request.GET.get('results_per_page', settings.HAYSTACK_SEARCH_RESULTS_PER_PAGE))
        return super(ChargeSearchView, self).build_page()

    def build_form(self, form_kwargs=None):
        if form_kwargs is None:
            form_kwargs = {}

        # This way the form can always receive a list containing zero or more
        # facet expressions:
        #form_kwargs['act_url'] = self.request.GET.get("act_url")

        return super(ChargeSearchView, self).build_form(form_kwargs)

    def _get_extended_selected_facets(self):
        """
        modifies the extended_selected_facets, adding correct labels for this view
        works directly on the extended_selected_facets dictionary
        """
        extended_selected_facets = super(ChargeSearchView, self)._get_extended_selected_facets()

        # this comes from the Mixins
        extended_selected_facets = self.add_date_interval_extended_selected_facets(extended_selected_facets, 'start_date')
        extended_selected_facets = self.add_date_interval_extended_selected_facets(extended_selected_facets, 'end_date')

        return extended_selected_facets

    def extra_context(self):
        """
        Add extra content here, when needed
        """
        extra = super(ChargeSearchView, self).extra_context()
        extra['base_url'] = reverse('om_charge_search') + '?' + extra['params'].urlencode()

        person_slug = self.request.GET.get('person', None)
        if person_slug:
            try:
                extra['person'] = Person.objects.get(slug=person_slug)
            except ObjectDoesNotExist:
                pass

        group_slug = self.request.GET.get('group', None)
        if group_slug:
            try:
                extra['group'] = Group.objects.get(slug=group_slug)
            except ObjectDoesNotExist:
                pass

        # get data about custom date range facets
        extra['facet_queries_start_date'] = self._get_custom_facet_queries_date('start_date')
        extra['facet_queries_end_date'] = self._get_custom_facet_queries_date('end_date')

        extra['facets_sorted'] = self.FACETS_SORTED
        extra['facets_labels'] = self.FACETS_LABELS

        paginator = Paginator(self.results, self.results_per_page)
        page = self.request.GET.get('page', 1)
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            page_obj = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            page_obj = paginator.page(paginator.num_pages)

        extra['paginator'] = paginator
        extra['page_obj'] = page_obj

        return extra
