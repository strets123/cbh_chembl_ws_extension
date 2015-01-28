from tastypie.resources import Resource
from tastypie.serializers import Serializer
from tastypie.serializers import XML_ENCODING
from tastypie.api import Api
from tastypie.exceptions import ImmediateHttpResponse
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from tastypie import http
from chembl_core_db.utils import plural
from tastypie.exceptions import UnsupportedFormat
from tastypie.exceptions import BadRequest
from StringIO import StringIO
from django.core.exceptions import ImproperlyConfigured
import mimeparse
from tastypie.utils.mime import build_content_type
import simplejson
from django.utils import six
from django.http import HttpResponse
from django.http import HttpResponseRedirect

import time
import logging
import django
import urlparse
from django.conf import settings
from django.http import HttpResponseNotFound
from tastypie.exceptions import NotFound
from django.views.generic import FormView, View
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout
from tastypie.resources import ModelResource

# If ``csrf_exempt`` isn't present, stub it.
try:
    from django.views.decorators.csrf import csrf_exempt
except ImportError:
    def csrf_exempt(func):
        return func

try:
    import defusedxml.lxml as lxml
    from defusedxml.common import DefusedXmlException
    from defusedxml.lxml import parse as parse_xml
    from lxml.etree import Element, tostring, LxmlError, XMLParser
except ImportError:
    lxml = None

try:
    TOP_LEVEL_PAGE = settings.TASTYPIE_TOP_LEVEL_PAGE
except AttributeError:
    TOP_LEVEL_PAGE = 'https://www.ebi.ac.uk/chembl/ws'

try:
    WS_DEBUG = settings.WS_DEBUG
except AttributeError:
    WS_DEBUG = False


from tastypie.authentication import SessionAuthentication

from tastypie.serializers import Serializer
from django.contrib.auth import get_user_model

import re
import json


class UserResource(ModelResource):
    class Meta:
        queryset = get_user_model().objects.all()
        resource_name = 'users'
        allowed_methods = ["get",] 
        excludes = ['email', 'password', 'is_active', 'is_staff', 'is_superuser']


    def apply_authorization_limits(self, request, object_list):
        return object_list.get(pk=request.user.id)







#-----------------------------------------------------------------------------------------------------------------------



class Login(FormView):
    form_class = AuthenticationForm
    template_name = "cbh_chembl_ws_extension/login.html"
    logout = None
    def get(self, request, *args, **kwargs):
        print AuthenticationForm()
        # logout = None
        # if logout in kwargs:
        #     logout = kwargs.pop("logout")
        #     print logout
        redirect_to = settings.LOGIN_REDIRECT_URL
        '''Borrowed from django base detail view'''
        # username = request.META.get('REMOTE_USER', None)
        # if not username:
        #     username = request.META.get('HTTP_X_WEBAUTH_USER', None)
        # if  username:
        #     return HttpResponseRedirect(reverse("webauth:login"))
        context = self.get_context_data(form=self.get_form(self.get_form_class()))
        context["logout"] = self.logout
        return self.render_to_response(context)


    def form_valid(self, form):
        redirect_to = settings.LOGIN_REDIRECT_URL
        auth_login(self.request, form.get_user())
        if self.request.session.test_cookie_worked():
            self.request.session.delete_test_cookie()
        return HttpResponseRedirect(redirect_to)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    # def dispatch(self, request, *args, **kwargs):
    #     request.session.set_test_cookie()
    #     return super(Login, self).dispatch(request, *args, **kwargs)

class Logout(View):
    def get(self, request, *args, **kwargs):
        auth_logout(request)
        return HttpResponseRedirect(settings.LOGOUT_REDIRECT_URL)



