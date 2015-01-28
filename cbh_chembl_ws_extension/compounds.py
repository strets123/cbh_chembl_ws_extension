from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from django.conf import settings
from tastypie.utils import trailing_slash
from django.conf.urls import *
from django.core.exceptions import ObjectDoesNotExist
from tastypie.authorization import Authorization
from tastypie import http
from django.http import HttpResponse
import base64
import time
from collections import OrderedDict
from tastypie.resources import ModelResource, Resource


try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem import Draw
except ImportError:
    Chem = None
    Draw = None
    AllChem = None

try:
    from rdkit.Chem.Draw import DrawingOptions
except ImportError:
    DrawingOptions = None

try:
    import indigo
    import indigo_renderer
except ImportError:
    indigo = None
    indigo_renderer = None


from tastypie.exceptions import BadRequest
from chembl_core_db.chemicalValidators import validateSmiles, validateChemblId, validateStandardInchiKey
from tastypie.utils.mime import build_content_type
from tastypie.exceptions import ImmediateHttpResponse
from django.db.utils import DatabaseError
from django.db import transaction
from django.db import connection
from chembl_beaker.beaker.core_apps.rasterImages.impl import _ctab2image
try:
    from chembl_compatibility.models import MoleculeDictionary
    from chembl_compatibility.models import CompoundMols
    from chembl_compatibility.models import MoleculeHierarchy
except ImportError:
    from chembl_core_model.models import MoleculeDictionary
    from chembl_core_model.models import CompoundMols
    from chembl_core_model.models import MoleculeHierarchy

try:
    DEFAULT_SYNONYM_SEPARATOR = settings.DEFAULT_COMPOUND_SEPARATOR
except AttributeError:
    DEFAULT_SYNONYM_SEPARATOR = ','

try:
    WS_DEBUG = settings.WS_DEBUG
except AttributeError:
    WS_DEBUG = False

from cbh_chembl_ws_extension.base import  CamelCaseJSONSerializer
from cbh_chembl_ws_extension.authorization import ProjectAuthorization

from tastypie.utils import dict_strip_unicode_keys
from tastypie.serializers import Serializer
from django.core.serializers.json import DjangoJSONEncoder
from tastypie import fields, utils
from cbh_chembl_model_extension.models import CBHCompoundBatch, CBHCompoundMultipleBatch, Project
from tastypie.authentication import SessionAuthentication
import json
from tastypie.paginator import Paginator
from chembl_beaker.beaker.core_apps.conversions.impl import _smiles2ctab, _apply

from flowjs.models import FlowFile
import xlrd
import pandas as pd
import numpy as np
import urllib




class ProjectResource(ModelResource):

    class Meta:
        queryset = Project.objects.all()
        authentication = SessionAuthentication()
        paginator_class = Paginator
        allowed_methods = ['get']        
        #serializer = CamelCaseJSONSerializer()
        resource_name = 'cbh_projects'
        #authorization = ProjectAuthorization()
        include_resource_uri = False
        default_format = 'application/json'

    def prepend_urls(self):
        return [
        url(r"^(?P<resource_name>%s)/$" % self._meta.resource_name,
                self.wrap_view('dispatch_list'), name="api_fetch_projects")
        ]

    def get_projects(self, request, **kwargs):

        self.build_bundle()

        return self.create_response(request, bundle, response_class=http.HttpCreated)






class MoleculeDictionaryResource(ModelResource):
    project = fields.ForeignKey(ProjectResource, 'project', blank=False, null=False)
    class Meta:    
        queryset = MoleculeDictionary.objects.all()
        resource_name = 'molecule_dictionaries'
        authorization = ProjectAuthorization()
        include_resource_uri = False
        allowed_methods = ['get', 'post', 'put']
        default_format = 'application/json'
        authentication = SessionAuthentication()
        paginator_class = Paginator






class CBHCompoundBatchResource(ModelResource):
    project = fields.ForeignKey(ProjectResource, 'project', blank=False, null=False)
    class Meta:
        filtering = {
            "std_ctab": ALL_WITH_RELATIONS,
            "ctab": ALL,
            "multiple_batch_id": ALL_WITH_RELATIONS,
        }
        always_return_data = True
        prefix = "related_molregno"
        fieldnames = [('chembl_id', 'chemblId'),
                  ('pref_name', 'preferredCompoundName'),
                  ('max_phase', 'knownDrug'),
                  ('compoundproperties.med_chem_friendly', 'medChemFriendly'),
                  ('compoundproperties.ro3_pass', 'passesRuleOfThree'),
                  ('compoundproperties.full_molformula', 'molecularFormula'),
                  ('compoundstructures.canonical_smiles', 'smiles'),
                  ('compoundstructures.standard_inchi_key', 'stdInChiKey'),
                  ('compoundproperties.molecular_species', 'species'),
                  ('compoundproperties.num_ro5_violations', 'numRo5Violations'),
                  ('compoundproperties.rtb', 'rotatableBonds'),
                  ('compoundproperties.mw_freebase', 'molecularWeight'),
                  ('compoundproperties.alogp', 'alogp'),
                  ('compoundproperties.acd_logp', 'acdLogp'),
                  ('compoundproperties.acd_logd', 'acdLogd'),
                  ('compoundproperties.acd_most_apka', 'acdAcidicPka'),
                  ('compoundproperties.acd_most_bpka', 'acdBasicPka')]
        queryset = CBHCompoundBatch.objects.all()
        resource_name = 'cbh_compound_batches'
        authorization = ProjectAuthorization()
        include_resource_uri = False
        serializer = CamelCaseJSONSerializer()
        allowed_methods = ['get', 'post', 'put']
        default_format = 'application/json'
        authentication = SessionAuthentication()
        paginator_class = Paginator



    def post_validate(self, request, **kwargs):
        """Runs the validation for a single or small set of molecules"""
        #self.authorized_update_detail(self.get_object_list(bundle.request), bundle)



        deserialized = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))
        deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle(data=dict_strip_unicode_keys(deserialized), request=request)
        if bundle.obj.pk:
            self.authorized_update_detail(self.get_object_list(bundle.request), bundle)
        else:
            self.authorized_create_detail(self.get_object_list(bundle.request), bundle)

        updated_bundle = self.obj_build(bundle, dict_strip_unicode_keys(deserialized))
        bundle.obj.validate()
        dictdata = bundle.obj.__dict__
        dictdata.pop("_state")
        
        updated_bundle = self.build_bundle(obj=bundle.obj, data=dictdata)
        return self.create_response(request, updated_bundle, response_class=http.HttpAccepted)

    def get_project_custom_field_names(self, request, **kwargs):
        # deserialized = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'text/plain'))
        
        # deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle(request=request)


        fields = CBHCompoundBatch.objects.get_all_keys()
        bundle.data['field_names'] =[{'name': item, 'count': 1, 'last_used': ''} for item in fields]      

        return "This needs moving to the project resource"
        #return self.create_response(request, bundle, response_class=http.HttpAccepted)


        #return HttpResponse("{ 'field_names': [ {'name': 'test1', 'count': 1, 'last_used': ''}, {'name': 'test2', 'count': 1, 'last_used': ''} ] }")


    def save_related(self, bundle):
        #bundle.obj.created_by = request.user.
        bundle.obj.generate_structure_and_dictionary()
        

    def alter_deserialized_detail_data(self, request, deserialized):
        proj = Project.objects.get(project_key=deserialized["project_key"])
        deserialized["project"] = proj
        return deserialized

    def full_hydrate(self, bundle):
        '''As the object is created we run the validate code on it'''
        bundle = super(CBHCompoundBatchResource, self).full_hydrate(bundle)
        bundle.obj.validate()
        return bundle


    def obj_build(self, bundle, kwargs):
        """
        A ORM-specific implementation of ``obj_create``.
        """
        bundle.obj = self._meta.object_class()
        for key, value in kwargs.items():
            setattr(bundle.obj, key, value)
        setattr(bundle.obj, "id", -1)
        
        return bundle

    def prepend_urls(self):
        return [
        url(r"^(?P<resource_name>%s)/validate/$" % self._meta.resource_name,
                self.wrap_view('post_validate'), name="api_validate_compound_batch"),
        url(r"^(?P<resource_name>%s)/validate_list/$" % self._meta.resource_name,
                self.wrap_view('post_validate_list'), name="api_validate_compound_list"),
        url(r"^(?P<resource_name>%s)/existing/$" % self._meta.resource_name,
                self.wrap_view('get_project_custom_field_names'), name="api_batch_existing_fields"),
                

        url(r"^(?P<resource_name>%s)/multi_batch_save/$" % self._meta.resource_name,
                self.wrap_view('multi_batch_save'), name="multi_batch_save"),
        url(r"^(?P<resource_name>%s)/multi_batch_custom_fields/$" % self._meta.resource_name,
                self.wrap_view('multi_batch_custom_fields'), name="multi_batch_custom_fields"),
        url(r"^(?P<resource_name>%s)/smiles2svg/(?P<structure>\w[\w-]*)/$" % 
                self._meta.resource_name, self.wrap_view('get_image_from_pipe'),name="smiles2svg")
        ]

    def multi_batch_save(self, request, **kwargs):
        deserialized = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))
        
        deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle(data=dict_strip_unicode_keys(deserialized), request=request)
        if bundle.obj.pk:
            self.authorized_update_detail(self.get_object_list(bundle.request), bundle)
        else:
            self.authorized_create_detail(self.get_object_list(bundle.request), bundle)
        id = bundle.data["current_batch"]
        batches = CBHCompoundMultipleBatch.objects.get(pk=id).uploaded_data
        bundle.data["saved"] = 0
        bundle.data["errors"] = []

        for batch in batches:
            try:

                batch.save(validate=False)
                batch.generate_structure_and_dictionary()
                bundle.data["saved"] += 1
            except Exception , e:
                bundle.data["errors"] += e

        return self.create_response(request, bundle, response_class=http.HttpCreated)


    def multi_batch_custom_fields(self, request, **kwargs):
        '''Save custom fields from the mapping section when adding ID/SMILES list'''
        deserialized = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))
        
        deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle(data=dict_strip_unicode_keys(deserialized), request=request)
        if bundle.obj.pk:
            self.authorized_update_detail(self.get_object_list(bundle.request), bundle)
        else:
            self.authorized_create_detail(self.get_object_list(bundle.request), bundle)
        id = bundle.data["current_batch"]

        mb = CBHCompoundMultipleBatch.objects.get(pk=id)
        for b in mb.uploaded_data:
            b.custom_fields = bundle.data["custom_fields"]
        mb.save()

        return self.create_response(request, bundle, response_class=http.HttpAccepted)



    def validate_multi_batch(self,multi_batch, bundle, request):
        total = len(multi_batch.uploaded_data)
        bundle.data["objects"] = {"pains" :[], "changed" : [], "errors" :[]}
        for batch in multi_batch.uploaded_data:

            batch = batch.__dict__
            batch.pop("_state")
            if batch["warnings"]["pains_count"] != "0":
                bundle.data["objects"]["pains"].append(batch)
            if batch["errors"] != {}:
                bundle.data["objects"]["errors"].append(batch)
                total = total - 1

            # if batch["warnings"]["hasChanged"].lower() == "true":
            #     bundle.data["objects"]["changed"].append(batch)  

        bundle.data["objects"]["total"] = total

        bundle.data["current_batch"] = multi_batch.pk
        return self.create_response(request, bundle, response_class=http.HttpAccepted)



    def post_validate_list(self, request, **kwargs):
        deserialized = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))
        
        deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle(data=dict_strip_unicode_keys(deserialized), request=request)
        if bundle.obj.pk:
            self.authorized_update_detail(self.get_object_list(bundle.request), bundle)
        else:
            self.authorized_create_detail(self.get_object_list(bundle.request), bundle)
        type = bundle.data.get("type",None).lower()
        objects =  bundle.data.get("objects", [])
       
        batches = []
        if type == "smiles":
            batches = [CBHCompoundBatch.objects.from_rd_mol(Chem.MolFromSmiles(obj), smiles=obj, project=bundle.data["project"]) for obj in objects ]

        elif type == "inchi":
            mols = _apply(objects,Chem.MolFromInchi)
            batches = [CBHCompoundBatch.objects.from_rd_mol(mol, smiles=Chem.MolToSmiles(mol), project=bundle.data["project"]) for mol in mols]
        # for b in batches:
        #     b["created_by"] = request.user.username

        multiple_batch = CBHCompoundMultipleBatch.objects.create()
        for b in batches:
            b.multiple_batch_id = multiple_batch.pk

        multiple_batch.uploaded_data=batches
        multiple_batch.save()
        return self.validate_multi_batch(multiple_batch, bundle, request)


    def dehydrate(self, bundle):

        try:
            data = bundle.obj.related_molregno
            for names in self.Meta.fieldnames:
                bundle.data[names[1]] = deepgetattr(data, names[0], None)

            mynames = ["editable_by","viewable_by", "warnings", "properties", "custom_fields", "errors"]
            for name in mynames:
                bundle.data[name] = json.loads(bundle.data[name]) 
        except:
            pass
    
        return bundle




    def get_object_list(self, request):
        return super(CBHCompoundBatchResource, self).get_object_list(request).select_related("related_molregno", "related_molregno__compound_properties")





def deepgetattr(obj, attr, ex):
    """Recurses through an attribute chain to get the ultimate value."""
    try:
        return reduce(getattr, attr.split('.'), obj)

    except:
        return ex










class CBHCompoundBatchUpload(ModelResource):

    class Meta:
        always_return_data = True
        queryset = FlowFile.objects.all()
        resource_name = 'cbh_batch_upload'
        authorization = Authorization()
        include_resource_uri = False
        allowed_methods = ['get', 'post', 'put']
        default_format = 'application/json'
        authentication = SessionAuthentication()

    def prepend_urls(self):
        return [
        url(r"^(?P<resource_name>%s)/headers/$" % self._meta.resource_name,
                self.wrap_view('return_headers'), name="api_compound_batch_headers"),
        ]

    def return_headers(self, request, **kwargs):
        deserialized = self.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))
        
        deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle(data=dict_strip_unicode_keys(deserialized), request=request)

        request_json = bundle.data

        file_name = request_json['file_name']
        correct_file = self.get_object_list(request).filter(original_filename=file_name)[0]
        headers = []
        header_json = { }
        #get this into a datastructure if excel

        #or just use rdkit if SD file
        if (correct_file.extension == ".sdf"):
            #read in the file
            suppl = Chem.ForwardSDMolSupplier(correct_file.file)

            #read the headers from the first molecule

            for mol in suppl:
                if mol is None: continue
                if not headers: 
                    headers = list(mol.GetPropNames())
                    break

        elif(correct_file.extension in (".xls", ".xlsx")):
            #read in excel file, use pandas to read the headers
            df = pd.read_excel(correct_file.file)
            headers = list(df)

        #this converts to json in preparation to be added to the response
        bundle.data["headers"] = headers

            #send back

        return self.create_response(request, bundle, response_class=http.HttpAccepted)


    # def get_object_list(self, request):
    #     return super(CBHCompoundBatchUpload, self).get_object_list(request).filter()
