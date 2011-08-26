# DDTSS-Django - A Django implementation of the DDTP/DDTSS website
# Copyright (C) 2011 Martijn van Oosterhout <kleptog@svana.org>
# See LICENCE file for details.

import hashlib
import string
import random
import time

from django import forms
from django.http import HttpResponseForbidden
from django.shortcuts import render_to_response, redirect
from django.http import Http404
from django.template import RequestContext
from django.contrib import messages
from ddtp.database.ddtss import with_db_session, Languages, PendingTranslation, PendingTranslationReview, Users, UserAuthority, DescriptionMilestone
from ddtp.ddtss.views import show_message_screen, get_user

@with_db_session
def view_admin(session, request):
    """ Handle the super admin page """

    user = get_user(request, session)

    if not user.superuser:
        return HttpResponseForbidden('<h1>Forbidden</h1>')

    langs = session.query(Languages).all()
    admins = session.query(Users).filter_by(superuser=True).all()

    context = {
        'languages': langs,
        'admins': admins,
    }
    return render_to_response("ddtss/admin.html", context,
                              context_instance=RequestContext(request))

class LanguageAdminForm(forms.Form):
    """
    A form that manages the superuser view of languages
    """

    def __init__(self, session, *args, **kwargs):
        super(LanguageAdminForm, self).__init__(*args, **kwargs)
        self.fields['milestone_high'].choices = [(x, x) for (x,) in ( session.query(DescriptionMilestone.milestone).distinct()) ]
        self.fields['milestone_medium'].choices = [(x, x) for (x,) in ( session.query(DescriptionMilestone.milestone).distinct()) ]
        self.fields['milestone_low'].choices = [(x, x) for (x,) in ( session.query(DescriptionMilestone.milestone).distinct()) ]

    language = forms.RegexField(label='Language code', regex=r'^\w\w(_\w\w)?$', help_text="Language code")
    name = forms.CharField(label="Name", max_length=30, help_text = "Human understandable name for language.")
    numreviewers = forms.RegexField(label='Number of Reviewer', regex=r'^\d$', help_text="Number of needed reviewer")
    login = forms.BooleanField(label="Require login", required=False, help_text="Require login for DDTSS")
    enabled = forms.BooleanField(label="Enabled", required=False, help_text="Enabled for DDTSS")
    milestone_high = forms.ChoiceField(label="1. Milestone", required=False, help_text="1. Milestone");
    milestone_medium = forms.ChoiceField(label="2. Milestone", required=False, help_text="2. Milestone");
    milestone_low = forms.ChoiceField(label="3. Milestone", required=False, help_text="3. Milestone");

@with_db_session
def view_admin_lang(session, request, language):
    """ Handle superuser language management """

    user = get_user(request, session)

    if not user.superuser:
        return HttpResponseForbidden('<h1>Forbidden</h1>')

    # Note: this is one of the few places where you're allowed to look at a disable language
    lang = session.query(Languages).get(language)
    if not lang:
        raise Http404()

    if request.method == "POST":
        if 'cancel' in request.POST:
            return redirect('ddtss_admin')
        if 'submit' in request.POST:
            form = LanguageAdminForm(session,data=request.POST)
            if form.is_valid():
                # Modify language
                lang.fullname = form.cleaned_data['name']
                lang.numreviewers = form.cleaned_data['numreviewers']
                lang.requirelogin = form.cleaned_data['login']
                lang.enabled_ddtss = form.cleaned_data['enabled']
                lang.milestone_high = form.cleaned_data['milestone_high']
                lang.milestone_medium = form.cleaned_data['milestone_medium']
                lang.milestone_low = form.cleaned_data['milestone_low']

                session.commit()

                return redirect('ddtss_admin')
        if 'add' in request.POST:
            # Add user as language coordinator
            new_user = session.query(Users).get(request.POST.get('username'))
            if not new_user:
                messages.error(request, 'User %r not found' % request.POST.get('username'))
            else:
                # User exists, add or update authority
                new_auth = new_user.get_authority(language)
                new_auth.auth_level = UserAuthority.AUTH_LEVEL_COORDINATOR
                session.add(new_auth)
                messages.info(request, 'User %s now coordinator' % new_user.username)
                session.commit()
        if 'del' in request.POST:
            # Remove user as language coordinator
            new_user = session.query(Users).get(request.POST.get('del'))
            if not new_user:
                messages.error(request, 'User %r not found' % request.POST.get('username'))
            else:
                # User exists, drop back to trusted user
                new_auth = new_user.get_authority(language)
                new_auth.auth_level = UserAuthority.AUTH_LEVEL_TRUSTED
                messages.info(request, 'User %s now only trusted' % new_user.username)
                session.commit()

    form = LanguageAdminForm(session,dict( \
        language=language, \
        name=lang.fullname, \
        numreviewers=lang.numreviewers, \
        login=lang.requirelogin, \
        enabled=lang.enabled_ddtss, \
        milestone_high=lang.milestone_high,\
        milestone_medium=lang.milestone_medium,\
        milestone_low=lang.milestone_low \
        ))

    return render_to_response("ddtss/admin_lang.html", { 'lang': lang, 'form': form },
                              context_instance=RequestContext(request))

class CoordinatorAdminForm(forms.Form):
    """
    A form that manages the superuser view of languages
    """

    def __init__(self, session, *args, **kwargs):
        super(CoordinatorAdminForm, self).__init__(*args, **kwargs)
        self.fields['milestone_high'].choices = [(x, x) for (x,) in ( session.query(DescriptionMilestone.milestone).distinct()) ]
        self.fields['milestone_medium'].choices = [(x, x) for (x,) in ( session.query(DescriptionMilestone.milestone).distinct()) ]
        self.fields['milestone_low'].choices = [(x, x) for (x,) in ( session.query(DescriptionMilestone.milestone).distinct()) ]

    numreviewers = forms.RegexField(label='Number of Reviewer', regex=r'^\d$', help_text="Number of needed reviewer")
    login = forms.BooleanField(label="Require login", required=False, help_text="Require login for DDTSS")
    milestone_high = forms.ChoiceField(label="1. Milestone", required=False, help_text="1. Milestone");
    milestone_medium = forms.ChoiceField(label="2. Milestone", required=False, help_text="2. Milestone");
    milestone_low = forms.ChoiceField(label="3. Milestone", required=False, help_text="3. Milestone");


@with_db_session
def view_coordinator(session, request, language):
    """ Handle coordinator language management """

    user = get_user(request, session)

    auth = user.get_authority(language)

    if auth.auth_level != auth.AUTH_LEVEL_COORDINATOR:
        return HttpResponseForbidden('<h1>Forbidden</h1>')

    lang = session.query(Languages).get(language)
    if not lang or not lang.enabled_ddtss:
        raise Http404()

    if request.method == "POST":
        if 'cancel' in request.POST:
            return redirect('ddtss_index_lang', language)
        if 'submit' in request.POST:
            form = CoordinatorAdminForm(session,data=request.POST)
            if form.is_valid():
                # Modify language
                lang.numreviewers = form.cleaned_data['numreviewers']
                lang.requirelogin = form.cleaned_data['login']
                lang.milestone_high = form.cleaned_data['milestone_high']
                lang.milestone_medium = form.cleaned_data['milestone_medium']
                lang.milestone_low = form.cleaned_data['milestone_low']

                session.commit()

                return redirect('ddtss_index_lang', language)
        if 'add' in request.POST:
            # Add user as language coordinator
            new_user = session.query(Users).get(request.POST.get('username'))
            if not new_user:
                messages.error(request, 'User %r not found' % request.POST.get('username'))
            else:
                # User exists, add or update authority
                new_auth = new_user.get_authority(language)
                new_auth.auth_level = UserAuthority.AUTH_LEVEL_TRUSTED
                session.add(new_auth)
                messages.info(request, 'User %s now trusted' % new_user.username)
                session.commit()
        if 'del' in request.POST:
            # Remove user as language coordinator
            new_user = session.query(Users).get(request.POST.get('del'))
            if not new_user:
                messages.error(request, 'User %r not found' % request.POST.get('username'))
            else:
                # User exists, drop back to trusted user
                new_auth = new_user.get_authority(language)
                new_auth.auth_level = UserAuthority.AUTH_LEVEL_NONE
                messages.info(request, 'User %s no longer trusted' % new_user.username)
                session.commit()

    form = CoordinatorAdminForm(session,dict(numreviewers=lang.numreviewers,\
                                     login=lang.requirelogin,\
                                     milestone_high=lang.milestone_high,\
                                     milestone_medium=lang.milestone_medium,\
                                     milestone_low=lang.milestone_low\
                                     ))

    return render_to_response("ddtss/coordinator.html", { 'lang': lang, 'form': form },
                              context_instance=RequestContext(request))
