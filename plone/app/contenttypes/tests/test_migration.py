# -*- coding: utf-8 -*-
from Products.CMFCore.utils import getToolByName
from five.intid.intid import IntIds
from five.intid.site import addUtility
from plone.app.contenttypes.testing import \
    PLONE_APP_CONTENTTYPES_MIGRATION_TESTING
from plone.event.interfaces import IEventAccessor
from plone.app.testing import login
from plone.app.testing import applyProfile
from zope.component import getSiteManager
from zope.component import getUtility
from zope.intid.interfaces import IIntIds
from zope.schema.interfaces import IVocabularyFactory

import os.path
import unittest2 as unittest


class MigrateToATContentTypesTest(unittest.TestCase):

    layer = PLONE_APP_CONTENTTYPES_MIGRATION_TESTING

    def setUp(self):
        self.portal = self.layer['portal']
        self.request = self.layer['request']
        self.request['ACTUAL_URL'] = self.portal.absolute_url()
        self.request['URL'] = self.portal.absolute_url()
        self.catalog = getToolByName(self.portal, "portal_catalog")
        self.portal.acl_users.userFolderAddUser('admin',
                                                'secret',
                                                ['Manager'],
                                                [])
        login(self.portal, 'admin')
        self.portal.portal_workflow.setDefaultChain(
            "simple_publication_workflow")

    def tearDown(self):
        try:
            applyProfile(self.portal, 'plone.app.contenttypes:uninstall')
        except KeyError:
            pass

    def get_test_image_data(self):
        test_image_path = os.path.join(os.path.dirname(__file__), 'image.png')
        with open(test_image_path, 'rb') as test_image_file:
            test_image_data = test_image_file.read()
        return test_image_data

    def get_migrator(self, obj, migrator_class):
        src_portal_type = migrator_class.src_portal_type
        dst_portal_type = migrator_class.dst_portal_type
        migrator = migrator_class(obj, src_portal_type=src_portal_type,
                                  dst_portal_type=dst_portal_type)
        return migrator

    def createATCTobject(self, klass, id, parent=None):
        '''Borrowed from ATCTFieldTestCase'''
        import transaction
        parent = parent if parent else self.portal
        obj = klass(oid=id)
        parent[id] = obj
        transaction.savepoint()
        # need to aq wrap after the savepoint. wrapped content can't be pickled
        obj = obj.__of__(parent)
        obj.initializeArchetype()
        return obj

    def createATCTBlobNewsItem(self, id, parent=None):
        from Products.Archetypes.atapi import StringField, TextField
        from Products.ATContentTypes.interface import IATNewsItem
        from archetypes.schemaextender.interfaces import ISchemaExtender
        from archetypes.schemaextender.field import ExtensionField
        from plone.app.blob.subtypes.image import ExtensionBlobField
        from zope.component import getGlobalSiteManager
        from zope.interface import implements

        # create schema extension
        class ExtensionTextField(ExtensionField, TextField):
            """ derivative of text for extending schemas """

        class ExtensionStringField(ExtensionField, StringField):
            """ derivative of text for extending schemas """

        class SchemaExtender(object):
            implements(ISchemaExtender)
            fields = [
                ExtensionTextField('text',
                                   primary=True,
                                   ),
                ExtensionBlobField('image',
                                   accessor='getImage',
                                   mutator='setImage',
                                   ),
                ExtensionStringField('imageCaption',
                                     ),
            ]

            def __init__(self, context):
                self.context = context

            def getFields(self):
                return self.fields

        # register adapter
        gsm = getGlobalSiteManager()
        gsm.registerAdapter(SchemaExtender, (IATNewsItem,), ISchemaExtender)

        # create content
        container = parent or self.portal
        container.invokeFactory('News Item', id)
        at_newsitem = container['newsitem']

        # unregister adapter assure test isolation
        gsm.unregisterAdapter(required=[IATNewsItem], provided=ISchemaExtender)

        return at_newsitem

    def test_patct_event_is_migrated(self):
        """Can we migrate a Products.ATContentTypes event?"""
        from DateTime import DateTime
        from plone.app.contenttypes.migration.migration import migrate_events
        from plone.app.event.dx.behaviors import IEventSummary

        # create an ATEvent
        self.portal.invokeFactory('Event', 'event')
        at_event = self.portal['event']

        # Date
        at_event.getField('startDate') \
                .set(at_event, DateTime('2013-02-03 12:00'))
        at_event.getField('endDate') \
                .set(at_event, DateTime('2013-04-05 13:00'))

        # Contact
        at_event.getField('contactPhone').set(at_event, '123456789')
        at_event.getField('contactEmail').set(at_event, 'dummy@email.com')
        at_event.getField('contactName').set(at_event, 'Name')

        # URL
        at_event.getField('eventUrl').set(at_event, 'http://www.plone.org')

        # Attendees
        at_event.getField('attendees').set(at_event, ('You', 'Me'))

        # Text
        at_event.setText('Tütensuppe')
        at_event.setContentType('text/plain')

        oldTZ = os.environ.get('TZ', None)
        os.environ['TZ'] = 'Asia/Tbilisi'

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrate_events(self.portal)

        if oldTZ:
            os.environ['TZ'] = oldTZ
        else:
            del os.environ['TZ']

        # assertions
        dx_event = self.portal['event']
        dx_acc = IEventAccessor(dx_event)
        self.assertEqual(
            "<class 'Products.ATContentTypes.content.event.ATEvent'>",
            str(at_event.__class__),
        )
        self.assertEqual(
            "<class 'plone.app.contenttypes.content.Event'>",
            str(dx_event.__class__),
        )
        self.assertEqual(2013, dx_acc.start.year)
        self.assertEqual(02, dx_acc.start.month)
        self.assertEqual(03, dx_acc.start.day)
        self.assertEqual(12, dx_acc.start.hour)
        self.assertEqual('Asia/Tbilisi', str(dx_acc.start.tzinfo))
        self.assertEqual(2013, dx_acc.end.year)
        self.assertEqual(04, dx_acc.end.month)
        self.assertEqual(05, dx_acc.end.day)
        self.assertEqual(13, dx_acc.end.hour)
        self.assertEqual('Asia/Tbilisi', str(dx_acc.end.tzinfo))
        self.assertEqual(u'Asia/Tbilisi', dx_acc.timezone)
        self.assertEqual('123456789', dx_acc.contact_phone)
        self.assertEqual('dummy@email.com', dx_acc.contact_email)
        self.assertEqual('Name', dx_acc.contact_name)
        self.assertEqual('http://www.plone.org', dx_acc.event_url)
        self.assertEqual(('You', 'Me'), dx_acc.attendees)
        self.assertEquals('Event', dx_event.__class__.__name__)
        self.assertEqual(u'<p>T\xfctensuppe</p>', dx_acc.text)
        self.assertEqual(u'Tütensuppe', IEventSummary(dx_event).text.raw)

    def test_pae_atevent_is_migrated(self):
        """Can we migrate a plone.app.event AT event?"""
        from DateTime import DateTime
        from plone.testing import z2
        from plone.app.testing import applyProfile
        from plone.app.contenttypes.migration.migration import migrate_events
        from plone.app.event.dx.behaviors import IEventSummary

        # Enable plone.app.event.at
        z2.installProduct(self.layer['app'], 'plone.app.event.at')
        applyProfile(self.portal, 'plone.app.event.at:default')

        self.portal.invokeFactory('Event', 'pae-at-event')
        old_event = self.portal['pae-at-event']

        # Date
        old_event.getField('startDate') \
                 .set(old_event, DateTime('2013-01-01 12:00'))
        old_event.getField('endDate') \
                 .set(old_event, DateTime('2013-02-01 13:00'))
        old_event.getField('wholeDay').set(old_event, False)
        old_event.getField('timezone').set(old_event, 'Asia/Tbilisi')

        # Contact
        old_event.getField('contactPhone').set(old_event, '123456789')
        old_event.getField('contactEmail').set(old_event, 'dummy@email.com')
        old_event.getField('contactName').set(old_event, 'Name')

        # URL
        old_event.getField('eventUrl').set(old_event, 'http://www.plone.org')

        # Attendees
        old_event.getField('attendees').set(old_event, ('You', 'Me'))

        # Text
        old_event.setText('Tütensuppe')
        old_event.setContentType('text/plain')

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrate_events(self.portal)

        # Compare new and old events
        new_event = self.portal['pae-at-event']
        new_event_acc = IEventAccessor(new_event)
        self.assertEqual(
            "<class 'plone.app.event.at.content.ATEvent'>",
            str(old_event.__class__),
        )
        self.assertEqual(
            "<class 'plone.app.contenttypes.content.Event'>",
            str(new_event.__class__),
        )
        self.assertEqual('Event', new_event.portal_type)
        self.assertEqual(2013, new_event_acc.start.year)
        self.assertEqual(01, new_event_acc.start.month)
        self.assertEqual(01, new_event_acc.start.day)
        self.assertEqual(12, new_event_acc.start.hour)
        self.assertEqual('Asia/Tbilisi', str(new_event_acc.start.tzinfo))
        self.assertEqual(2013, new_event_acc.end.year)
        self.assertEqual(02, new_event_acc.end.month)
        self.assertEqual(01, new_event_acc.end.day)
        self.assertEqual(13, new_event_acc.end.hour)
        self.assertEqual('Asia/Tbilisi', str(new_event_acc.end.tzinfo))
        self.assertEqual(u'Asia/Tbilisi', new_event_acc.timezone)
        self.assertEqual(u'Name', new_event_acc.contact_name)
        self.assertEqual(u'dummy@email.com', new_event_acc.contact_email)
        self.assertEqual(u'123456789', new_event_acc.contact_phone)
        self.assertEqual(u'http://www.plone.org', new_event_acc.event_url)
        self.assertEqual(u'<p>T\xfctensuppe</p>', new_event_acc.text)
        self.assertEqual(u'Tütensuppe', IEventSummary(new_event).text.raw)

    def test_pae_dxevent_is_migrated(self):
        from datetime import datetime
        from plone.app.contenttypes.migration.migration import migrate_events
        from plone.app.textfield.value import RichTextValue
        from plone.app.event.dx.behaviors import IEventSummary

        # Enable plone.app.event.dx
        from plone.app.testing import applyProfile
        applyProfile(self.portal, 'plone.app.event.dx:default')

        old_event = self.portal[self.portal.invokeFactory(
            'plone.app.event.dx.event',
            'dx-event',
            start=datetime(2011, 11, 11, 11, 0),
            end=datetime(2011, 11, 11, 12, 0),
            timezone="Asia/Tbilisi",
            whole_day=False,
        )]
        old_event_acc = IEventAccessor(old_event)
        old_event_acc.contact_name = 'George'
        old_event_acc.contact_email = 'me@geor.ge'
        old_event_acc.contact_phone = '+99512345'
        old_event_acc.event_url = 'http://geor.ge/event'
        old_event_acc.text = RichTextValue(
            raw='Woo, yeah',
            mimeType='text/plain',
            outputMimeType='text/x-html-safe'
        )

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrate_events(self.portal)

        # Compare new and old events
        new_event = self.portal['dx-event']
        new_event_acc = IEventAccessor(new_event)
        self.assertEqual(False, old_event.exclude_from_nav)
        self.assertEqual('Event', new_event.portal_type)
        self.assertEqual(2011, new_event_acc.start.year)
        self.assertEqual(11, new_event_acc.start.month)
        self.assertEqual(11, new_event_acc.start.day)
        self.assertEqual(11, new_event_acc.start.hour)
        self.assertEqual('Asia/Tbilisi', str(new_event_acc.start.tzinfo))
        self.assertEqual(2011, new_event_acc.end.year)
        self.assertEqual(11, new_event_acc.end.month)
        self.assertEqual(11, new_event_acc.end.day)
        self.assertEqual(12, new_event_acc.end.hour)
        self.assertEqual('Asia/Tbilisi', str(new_event_acc.end.tzinfo))
        self.assertEqual(u'Asia/Tbilisi', new_event_acc.timezone)
        self.assertEqual(u'George', new_event_acc.contact_name)
        self.assertEqual(u'me@geor.ge', new_event_acc.contact_email)
        self.assertEqual(u'+99512345', new_event_acc.contact_phone)
        self.assertEqual(u'http://geor.ge/event', new_event_acc.event_url)
        self.assertEqual(u'<p>Woo, yeah</p>', new_event_acc.text)
        self.assertEqual('Woo, yeah', IEventSummary(new_event).text.raw)
        self.assertEqual(False, new_event.exclude_from_nav)

    def test_pact_1_0_dxevent_is_migrated(self):
        from datetime import datetime
        from pytz import timezone
        from plone.app.contenttypes.migration.migration import migrate_events
        from plone.app.textfield.value import RichTextValue
        from plone.app.event.dx.behaviors import IEventSummary

        # Create a 1.0 Event object
        applyProfile(self.portal, 'plone.app.contenttypes.tests:1_0_x')
        old_event = self.portal[self.portal.invokeFactory(
            'Event',
            'dx-event',
            location='Newbraska',
            start_date=datetime(2019, 04, 02, 15, 20,
                                tzinfo=timezone('Asia/Tbilisi')),
            end_date=datetime(2019, 04, 02, 16, 20,
                              tzinfo=timezone('Asia/Tbilisi')),
            attendees='Me & You',
            event_url='http://woo.com',
            contact_name='Frank',
            contact_email='me@fra.nk',
            contact_phone='+4412345',
        )]
        old_event.text = RichTextValue(
            raw=u'Awesüme',
            mimeType='text/plain',
            outputMimeType='text/x-html-safe'
        )

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrate_events(self.portal)

        # Compare new and old events
        new_event = self.portal['dx-event']
        new_event_acc = IEventAccessor(new_event)
        self.assertEqual(False, old_event.exclude_from_nav)
        self.assertEqual('Event', new_event.portal_type)
        self.assertEqual(2019, new_event_acc.start.year)
        self.assertEqual(04, new_event_acc.start.month)
        self.assertEqual(02, new_event_acc.start.day)
        self.assertEqual(15, new_event_acc.start.hour)
        self.assertEqual('Asia/Tbilisi', str(new_event_acc.start.tzinfo))
        self.assertEqual(2019, new_event_acc.end.year)
        self.assertEqual(04, new_event_acc.end.month)
        self.assertEqual(02, new_event_acc.end.day)
        self.assertEqual(16, new_event_acc.end.hour)
        self.assertEqual('Asia/Tbilisi', str(new_event_acc.end.tzinfo))
        self.assertEqual(u'Asia/Tbilisi', new_event_acc.timezone)
        self.assertEqual(u'Frank', new_event_acc.contact_name)
        self.assertEqual(u'Newbraska', new_event_acc.location)
        self.assertEqual(u'me@fra.nk', new_event_acc.contact_email)
        self.assertEqual(u'+4412345', new_event_acc.contact_phone)
        self.assertEqual(u'http://woo.com', new_event_acc.event_url)
        self.assertEqual(u'<p>Awesüme</p>', new_event_acc.text)
        self.assertEqual(u'Awesüme', IEventSummary(new_event).text.raw)
        self.assertEqual(False, new_event.exclude_from_nav)

    def test_dx_excl_from_nav_is_migrated(self):
        from datetime import datetime
        from plone.app.contenttypes.migration.migration import DXEventMigrator

        # Enable plone.app.event.dx
        from plone.app.testing import applyProfile
        applyProfile(self.portal, 'plone.app.event.dx:default')

        old_event = self.portal[self.portal.invokeFactory(
            'plone.app.event.dx.event',
            'dx-event',
            start=datetime(2011, 11, 11, 11, 0),
            end=datetime(2011, 11, 11, 12, 0),
            timezone="GMT",
            whole_day=False,
            exclude_from_nav=True,
        )]

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(old_event, DXEventMigrator)
        migrator.migrate()

        new_event = self.portal['dx-event']
        self.assertEqual(True, old_event.exclude_from_nav)
        self.assertEqual(True, new_event.exclude_from_nav)

    def test_assert_at_contenttypes(self):
        from plone.app.contenttypes.interfaces import IDocument
        self.portal.invokeFactory('Document', 'document')
        at_document = self.portal['document']
        self.assertEqual('ATDocument', at_document.meta_type)
        self.assertFalse(IDocument.providedBy(at_document))

    def test_dx_content_is_indexed(self):
        from plone.app.contenttypes.migration.migration import DocumentMigrator
        from plone.app.contenttypes.interfaces import IDocument
        self.portal.invokeFactory('Document', 'document')
        at_document = self.portal['document']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_document, DocumentMigrator)
        migrator.migrate()
        brains = self.catalog(object_provides=IDocument.__identifier__)
        self.assertEqual(len(brains), 1)
        self.assertEqual(brains[0].getObject(), self.portal["document"])

    def test_old_content_is_removed(self):
        from plone.app.contenttypes.migration.migration import DocumentMigrator
        self.portal.invokeFactory('Document', 'document')
        at_document = self.portal['document']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_document, DocumentMigrator)
        migrator.migrate()
        brains = self.catalog(portal_type='Document')
        self.assertEqual(len(brains), 1)

    def test_old_content_is_unindexed(self):
        from Products.ATContentTypes.interfaces import IATDocument
        from plone.app.contenttypes.migration.migration import DocumentMigrator
        self.portal.invokeFactory('Document', 'document')
        at_document = self.portal['document']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_document, DocumentMigrator)
        brains = self.catalog(object_provides=IATDocument.__identifier__)
        self.assertEqual(len(brains), 1)
        migrator.migrate()
        brains = self.catalog(object_provides=IATDocument.__identifier__)
        self.assertEqual(len(brains), 0)

    def test_document_is_migrated(self):
        from plone.app.contenttypes.migration.migration import DocumentMigrator
        from plone.app.contenttypes.interfaces import IDocument
        self.portal.invokeFactory('Document', 'document')
        at_document = self.portal['document']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_document, DocumentMigrator)
        migrator.migrate()
        dx_document = self.portal['document']
        self.assertTrue(IDocument.providedBy(dx_document))
        self.assertTrue(at_document is not dx_document)

    def test_collection_is_migrated(self):
        from plone.app.contenttypes.migration.migration import\
            CollectionMigrator
        from plone.app.contenttypes.interfaces import ICollection
        if 'Collection' in self.portal.portal_types.keys():
            self.portal.invokeFactory('Collection', 'collection')
            at_collection = self.portal['collection']
            applyProfile(self.portal, 'plone.app.contenttypes:default')
            migrator = self.get_migrator(at_collection, CollectionMigrator)
            migrator.migrate()
            dx_collection = self.portal['collection']
            self.assertTrue(ICollection.providedBy(dx_collection))
            self.assertTrue(at_collection is not dx_collection)

    def test_document_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import DocumentMigrator
        from plone.app.textfield.interfaces import IRichTextValue

        # create an ATDocument
        self.portal.invokeFactory('Document', 'document')
        at_document = self.portal['document']
        at_document.setText('Tütensuppe')
        at_document.setContentType('chemical/x-gaussian-checkpoint')

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_document, DocumentMigrator)
        migrator.migrate()

        # assertions
        dx_document = self.portal['document']
        self.assertTrue(IRichTextValue(dx_document.text))
        self.assertEqual(dx_document.text.raw, u'Tütensuppe')
        self.assertEqual(dx_document.text.mimeType,
                         'chemical/x-gaussian-checkpoint')
        self.assertEqual(dx_document.text.outputMimeType, 'text/x-html-safe')

    def test_document_excludefromnav_is_migrated(self):
        from plone.app.contenttypes.migration.migration import DocumentMigrator

        # create an ATDocument
        self.portal.invokeFactory('Document', 'document')
        at_document = self.portal['document']
        at_document.setExcludeFromNav(True)

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_document, DocumentMigrator)
        migrator.migrate()

        # assertions
        dx_document = self.portal['document']
        self.assertTrue(dx_document.exclude_from_nav)

    def test_file_is_migrated(self):
        from Products.ATContentTypes.content.file import ATFile
        from plone.app.contenttypes.migration.migration import FileMigrator
        from plone.app.contenttypes.interfaces import IFile
        at_file = self.createATCTobject(ATFile, 'file')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_file, FileMigrator)
        migrator.migrate()
        dx_file = self.portal['file']
        self.assertTrue(IFile.providedBy(dx_file))
        self.assertTrue(at_file is not dx_file)

    def test_file_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import FileMigrator
        from plone.namedfile.interfaces import INamedBlobFile
        from Products.ATContentTypes.content.file import ATFile
        at_file = self.createATCTobject(ATFile, 'file')
        field = at_file.getField('file')
        field.set(at_file, 'dummydata')
        field.setFilename(at_file, 'dummyfile.txt')
        field.setContentType(at_file, 'text/dummy')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_file, FileMigrator)
        migrator.migrate()
        dx_file = self.portal['file']
        self.assertTrue(INamedBlobFile.providedBy(dx_file.file))
        self.assertEqual(dx_file.file.filename, 'dummyfile.txt')
        self.assertEqual(dx_file.file.contentType, 'text/dummy')
        self.assertEqual(dx_file.file.data, 'dummydata')

    def test_image_is_migrated(self):
        from Products.ATContentTypes.content.image import ATImage
        from plone.app.contenttypes.migration.migration import ImageMigrator
        from plone.app.contenttypes.interfaces import IImage
        at_image = self.createATCTobject(ATImage, 'image')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_image, ImageMigrator)
        migrator.migrate()
        dx_image = self.portal['image']
        self.assertTrue(IImage.providedBy(dx_image))
        self.assertTrue(at_image is not dx_image)

    def test_empty_image_is_migrated(self):
        """
        This should not happened cause the image field is required,
        but this is a special case in AT's FileField.
        """
        from Products.ATContentTypes.content.image import ATImage
        from plone.app.contenttypes.migration.migration import ImageMigrator
        at_image = self.createATCTobject(ATImage, 'image')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_image, ImageMigrator)
        migrator.migrate()
        dx_image = self.portal['image']
        self.assertEqual(dx_image.image, None)

    def test_image_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import ImageMigrator
        from plone.namedfile.interfaces import INamedBlobImage
        from Products.ATContentTypes.content.image import ATImage
        at_image = self.createATCTobject(ATImage, 'image')
        test_image_data = self.get_test_image_data()
        field = at_image.getField('image')
        field.set(at_image, test_image_data)
        field.setFilename(at_image, 'testimage.png')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_image, ImageMigrator)
        migrator.migrate()
        dx_image = self.portal['image']
        self.assertTrue(INamedBlobImage.providedBy(dx_image.image))
        self.assertEqual(dx_image.image.filename, 'testimage.png')
        self.assertEqual(dx_image.image.contentType, 'image/png')
        self.assertEqual(dx_image.image.data, test_image_data)

    def test_blob_file_is_migrated(self):
        from plone.app.contenttypes.migration.migration import BlobFileMigrator
        from plone.app.contenttypes.interfaces import IFile
        self.portal.invokeFactory('File', 'file')
        at_file = self.portal['file']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_file, BlobFileMigrator)
        migrator.migrate()
        dx_file = self.portal['file']
        self.assertTrue(IFile.providedBy(dx_file))
        self.assertTrue(at_file is not dx_file)

    def test_blob_file_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import BlobFileMigrator
        from plone.namedfile.interfaces import INamedBlobFile
        self.portal.invokeFactory('File', 'file')
        at_file = self.portal['file']
        at_file.setFile('dummydata',
                        mimetype="text/dummy",
                        filename='dummyfile.txt')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_file, BlobFileMigrator)
        migrator.migrate()
        dx_file = self.portal['file']
        self.assertTrue(INamedBlobFile.providedBy(dx_file.file))
        self.assertEqual(dx_file.file.filename, 'dummyfile.txt')
        self.assertEqual(dx_file.file.contentType, 'text/dummy')
        self.assertEqual(dx_file.file.data, 'dummydata')

    def test_blob_image_is_migrated(self):
        from plone.app.contenttypes.migration.migration import\
            BlobImageMigrator
        from plone.app.contenttypes.interfaces import IImage
        self.portal.invokeFactory('Image', 'image')
        at_image = self.portal['image']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_image, BlobImageMigrator)
        migrator.migrate()
        dx_image = self.portal['image']
        self.assertTrue(IImage.providedBy(dx_image))
        self.assertTrue(at_image is not dx_image)

    def test_empty_blob_image_is_migrated(self):
        """
        This should not happened cause the image field is required,
        but this is a special case in AT's FileField.
        """
        from plone.app.contenttypes.migration.migration import\
            BlobImageMigrator
        self.portal.invokeFactory('Image', 'image')
        at_image = self.portal['image']
        migrator = self.get_migrator(at_image, BlobImageMigrator)
        migrator.migrate()
        dx_image = self.portal['image']
        self.assertEqual(dx_image.image.data, '')

    def test_blob_image_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import\
            BlobImageMigrator
        from plone.namedfile.interfaces import INamedBlobImage
        self.portal.invokeFactory('Image', 'image')
        at_image = self.portal['image']
        test_image_data = self.get_test_image_data()
        at_image.setImage(test_image_data, filename='testimage.png')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_image, BlobImageMigrator)
        migrator.migrate()
        dx_image = self.portal['image']
        self.assertTrue(INamedBlobImage.providedBy(dx_image.image))
        self.assertEqual(dx_image.image.filename, 'testimage.png')
        self.assertEqual(dx_image.image.contentType, 'image/png')
        self.assertEqual(dx_image.image.data, test_image_data)

    def test_link_is_migrated(self):
        from plone.app.contenttypes.migration.migration import LinkMigrator
        from plone.app.contenttypes.interfaces import ILink
        self.portal.invokeFactory('Link', 'link')
        at_link = self.portal['link']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_link, LinkMigrator)
        migrator.migrate()
        dx_link = self.portal['link']
        self.assertTrue(ILink.providedBy(dx_link))
        self.assertTrue(dx_link is not at_link)

    def test_link_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import LinkMigrator
        from plone.app.contenttypes.interfaces import ILink
        self.portal.invokeFactory('Link', 'link')
        at_link = self.portal['link']
        field = at_link.getField('remoteUrl')
        field.set(at_link, 'http://plone.org')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_link, LinkMigrator)
        migrator.migrate()
        dx_link = self.portal['link']
        self.assertTrue(ILink.providedBy(dx_link.link))
        self.assertEqual(dx_link.link.remoteUrl, u'http://plone.org')

    def test_newsitem_is_migrated(self):
        from plone.app.contenttypes.migration.migration import NewsItemMigrator
        from plone.app.contenttypes.interfaces import INewsItem
        self.portal.invokeFactory('News Item', 'newsitem')
        at_newsitem = self.portal['newsitem']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_newsitem, NewsItemMigrator)
        migrator.migrate()
        dx_newsitem = self.portal['newsitem']
        self.assertTrue(INewsItem.providedBy(dx_newsitem))
        self.assertTrue(at_newsitem is not dx_newsitem)

    def test_newsitem_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import NewsItemMigrator
        from plone.app.textfield.interfaces import IRichTextValue
        from plone.namedfile.interfaces import INamedBlobImage

        # create an ATNewsItem
        self.portal.invokeFactory('News Item', 'newsitem')
        at_newsitem = self.portal['newsitem']
        at_newsitem.setText('Tütensuppe')
        at_newsitem.setContentType('chemical/x-gaussian-checkpoint')
        at_newsitem.setImageCaption('Daniel Düsentrieb')
        test_image_data = self.get_test_image_data()
        image_field = at_newsitem.getField('image')
        image_field.set(at_newsitem, test_image_data)
        image_field.setFilename(at_newsitem, 'testimage.png')

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_newsitem, NewsItemMigrator)
        migrator.migrate()

        # assertions
        dx_newsitem = self.portal['newsitem']
        self.assertTrue(INamedBlobImage.providedBy(dx_newsitem.image))
        self.assertEqual(dx_newsitem.image.filename, 'testimage.png')
        self.assertEqual(dx_newsitem.image.contentType, 'image/png')
        self.assertEqual(dx_newsitem.image.data, test_image_data)

        self.assertEqual(dx_newsitem.image_caption, u'Daniel Düsentrieb')

        self.assertTrue(IRichTextValue(dx_newsitem.text))
        self.assertEqual(dx_newsitem.text.raw, u'Tütensuppe')
        self.assertEqual(dx_newsitem.text.mimeType,
                         'chemical/x-gaussian-checkpoint')
        self.assertEqual(dx_newsitem.text.outputMimeType, 'text/x-html-safe')

    def test_blob_newsitem_is_migrated(self):
        from plone.app.contenttypes.migration.migration import\
            BlobNewsItemMigrator
        from plone.app.contenttypes.interfaces import INewsItem
        at_newsitem = self.createATCTBlobNewsItem('newsitem')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_newsitem, BlobNewsItemMigrator)
        migrator.migrate()
        dx_newsitem = self.portal['newsitem']
        self.assertTrue(INewsItem.providedBy(dx_newsitem))
        self.assertTrue(at_newsitem is not dx_newsitem)

    def test_blob_newsitem_content_is_migrated(self):
        from plone.app.contenttypes.migration.migration import \
            BlobNewsItemMigrator
        from plone.app.textfield.interfaces import IRichTextValue
        from plone.namedfile.interfaces import INamedBlobImage

        # create a BlobATNewsItem
        at_newsitem = self.createATCTBlobNewsItem('newsitem')
        at_newsitem.setText('Tütensuppe')
        at_newsitem.setContentType('chemical/x-gaussian-checkpoint')
        at_newsitem.setImageCaption('Daniel Düsentrieb')
        test_image_data = self.get_test_image_data()
        at_newsitem.setImage(test_image_data, filename='testimage.png')

        # migrate
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_newsitem, BlobNewsItemMigrator)
        migrator.migrate()
        dx_newsitem = self.portal['newsitem']

        # assertions
        self.assertTrue(INamedBlobImage.providedBy(dx_newsitem.image))
        self.assertEqual(dx_newsitem.image.filename, 'testimage.png')
        self.assertEqual(dx_newsitem.image.contentType, 'image/png')
        self.assertEqual(dx_newsitem.image.data, test_image_data)

        self.assertEqual(dx_newsitem.image_caption, u'Daniel Düsentrieb')

        self.assertTrue(IRichTextValue(dx_newsitem.text))
        self.assertEqual(dx_newsitem.text.raw, u'Tütensuppe')
        self.assertEqual(dx_newsitem.text.mimeType,
                         'chemical/x-gaussian-checkpoint')

    def test_folder_is_migrated(self):
        from plone.app.contenttypes.migration.migration import FolderMigrator
        from plone.app.contenttypes.interfaces import IFolder
        self.portal.invokeFactory('Folder', 'folder')
        at_folder = self.portal['folder']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_folder, FolderMigrator)
        migrator.migrate()
        dx_folder = self.portal['folder']
        self.assertTrue(IFolder.providedBy(dx_folder))
        self.assertTrue(at_folder is not dx_folder)

    def test_folder_children_are_migrated(self):
        from plone.app.contenttypes.migration.migration import FolderMigrator
        self.portal.invokeFactory('Folder', 'folder')
        at_folder = self.portal['folder']
        at_folder.invokeFactory('Document', 'document')
        at_child = at_folder['document']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrator = self.get_migrator(at_folder, FolderMigrator)
        migrator.migrate()
        dx_folder = self.portal['folder']
        self.assertTrue(at_child in dx_folder.contentValues())

    def test_relations_are_migrated(self):
        from plone.app.contenttypes.migration.migration import (
            restoreReferences,
            migrate_documents,
        )

        # IIntIds is not registered in the test env. So register it here
        sm = getSiteManager(self.portal)
        addUtility(sm, IIntIds, IntIds, ofs_name='intids', findroot=False)

        # create ATDocuments
        self.portal.invokeFactory('Document', 'doc1')
        at_doc1 = self.portal['doc1']
        self.portal.invokeFactory('Document', 'doc2')
        at_doc2 = self.portal['doc2']
        self.portal.invokeFactory('Document', 'doc3')
        at_doc3 = self.portal['doc3']
        self.portal.invokeFactory('News Item', 'newsitem')
        at_newsitem = self.portal['newsitem']

        # relate them
        at_doc1.setRelatedItems([at_doc2])
        at_doc2.setRelatedItems([at_newsitem, at_doc3, at_doc1])
        at_doc3.setRelatedItems(at_doc1)

        # migrate content
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrate_documents(self.portal)
        dx_doc1 = self.portal['doc1']
        dx_doc2 = self.portal['doc2']
        dx_doc3 = self.portal['doc3']

        # migrate references
        restoreReferences(self.portal)

        # assert single references
        dx_doc1_related = [x.to_object for x in dx_doc1.relatedItems]
        self.assertEqual(dx_doc1_related, [dx_doc2])

        dx_doc3_related = [x.to_object for x in dx_doc3.relatedItems]
        self.assertEqual(dx_doc3_related, [dx_doc1])

        # assert multi references, order is not restored
        dx_doc2_related = [x.to_object for x in dx_doc2.relatedItems]
        self.assertEqual(dx_doc2_related, [dx_doc1, at_newsitem, dx_doc3])

    def test_stats(self):
        from plone.app.contenttypes.migration.migration import DocumentMigrator
        from plone.app.contenttypes.migration.browser import \
            MigrateFromATContentTypes as MigrationView

        self.portal.invokeFactory('Document', 'doc1')
        at_doc1 = self.portal['doc1']
        self.portal.invokeFactory('Document', 'doc2')
        at_doc2 = self.portal['doc2']
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrationview = MigrationView(self.portal, None)
        stats = migrationview.stats()
        self.assertEqual(str(stats), "[('ATDocument', 2)]")
        migrator = self.get_migrator(at_doc1, DocumentMigrator)
        migrator.migrate()
        stats = migrationview.stats()
        self.assertEqual(str(stats), "[('ATDocument', 1), ('Document', 1)]")
        migrator = self.get_migrator(at_doc2, DocumentMigrator)
        migrator.migrate()
        stats = migrationview.stats()
        self.assertEqual(str(stats), "[('Document', 2)]")

    def test_migration_atctypes_vocabulary_registered(self):
        name = 'plone.app.contenttypes.migration.atctypes'
        factory = getUtility(IVocabularyFactory, name)
        self.assertIsNotNone(factory,
                             'Vocabulary %s does not exist' % name)

        vocabulary = factory(self.portal)
        self.assertEqual((), tuple(vocabulary))

    def test_migration_atctypes_vocabulary_result(self):
        from Products.ATContentTypes.content.document import ATDocument
        from Products.ATContentTypes.content.file import ATFile
        from Products.ATContentTypes.content.image import ATImage
        from Products.ATContentTypes.content.folder import ATFolder
        from Products.ATContentTypes.content.link import ATLink

        name = 'plone.app.contenttypes.migration.atctypes'
        factory = getUtility(IVocabularyFactory, name)

        self.createATCTobject(ATDocument, 'doc1')
        self.createATCTobject(ATDocument, 'doc2')
        self.createATCTobject(ATFile, 'file')
        self.createATCTobject(ATImage, 'image')
        self.createATCTobject(ATFolder, 'folder')
        self.createATCTobject(ATLink, 'link')

        vocabulary = factory(self.portal)

        self.assertEqual(
            5,
            len(vocabulary),
            'Expect 5 entries in vocab because there are 5 diffrent types')

        # Result format
        docs = [term for term in vocabulary if term.token == 'Document'][0]
        self.assertEqual('Document', docs.value)
        self.assertEqual('Document (2)', docs.title)

    def test_migration_extendedtypes_vocabulary_registered(self):
        name = 'plone.app.contenttypes.migration.extendedtypes'
        factory = getUtility(IVocabularyFactory, name)
        self.assertIsNotNone(factory,
                             'Vocabulary %s does not exist' % name)

        vocabulary = factory(self.portal)
        self.assertEqual((), tuple(vocabulary))

    def test_migration_extendedtypes_vocabulary_result(self):
        from archetypes.schemaextender.extender import CACHE_ENABLED
        from archetypes.schemaextender.extender import CACHE_KEY
        from archetypes.schemaextender.field import ExtensionField
        from archetypes.schemaextender.interfaces import ISchemaExtender
        from Products.Archetypes import atapi
        from Products.ATContentTypes.content.document import ATDocument
        from zope.component import adapts
        from zope.component import provideAdapter
        from zope.interface import classImplements
        from zope.interface import implements
        from zope.interface import Interface

        name = 'plone.app.contenttypes.migration.extendedtypes'
        factory = getUtility(IVocabularyFactory, name)

        class IDummy(Interface):
            """Taggable content
            """

        classImplements(ATDocument, IDummy)
        doc = self.createATCTobject(ATDocument, 'doc')

        class DummyField(ExtensionField, atapi.StringField):
            """Dummy Field"""

        class DummySchemaExtender(object):
            implements(ISchemaExtender)
            adapts(IDummy)

            _fields = [DummyField('dummy')]

            def __init__(self, context):
                self.context = context

            def getFields(self):
                return self._fields

        provideAdapter(DummySchemaExtender, name=u"dummy.extender")

        # Clear cache
        if CACHE_ENABLED:
            delattr(self.request, CACHE_KEY)
        self.assertIn('dummy', doc.Schema()._names)

        vocabulary = factory(self.portal)

        self.assertEqual(1, len(vocabulary), 'Expect one entry')

        self.assertEqual("Document (1) - extended fields: 'dummy'",
                         tuple(vocabulary)[0].title)

    def test_migrate_function(self):
        from plone.app.contenttypes.migration.migration import migrate
        from plone.app.contenttypes.migration.migration import DocumentMigrator
        self.portal.invokeFactory('Document', 'document')
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrate(self.portal, DocumentMigrator)
        dx_document = self.portal["document"]
        self.assertEqual(dx_document.meta_type, 'Dexterity Item')

    def test_migrate_xx_functions(self):
        from Products.ATContentTypes.content.image import ATImage
        from Products.ATContentTypes.content.file import ATFile
        from plone.app.contenttypes.migration.migration import (
            migrate_documents,
            migrate_collections,
            migrate_images,
            migrate_blobimages,
            migrate_files,
            migrate_blobfiles,
            migrate_links,
            migrate_newsitems,
            migrate_blobnewsitems,
            migrate_folders,
            migrate_events,
        )

        # create all content types
        self.portal.invokeFactory('Document', 'document')
        self.portal.invokeFactory('Image', 'image')
        self.createATCTobject(ATImage, 'blobimage')
        self.portal.invokeFactory('File', 'blobfile')
        self.createATCTobject(ATFile, 'file')
        self.portal.invokeFactory('Collection', 'collection')
        self.portal.invokeFactory('Link', 'link')
        self.portal.invokeFactory('News Item', 'newsitem')
        self.createATCTBlobNewsItem('blobnewsitem')
        self.portal.invokeFactory('Folder', 'folder')
        self.portal.invokeFactory('Event', 'event')

        # migrate all
        applyProfile(self.portal, 'plone.app.contenttypes:default')
        migrate_documents(self.portal)
        migrate_collections(self.portal)
        migrate_images(self.portal)
        migrate_blobimages(self.portal)
        migrate_files(self.portal)
        migrate_blobfiles(self.portal)
        migrate_links(self.portal)
        migrate_newsitems(self.portal)
        migrate_blobnewsitems(self.portal)
        migrate_folders(self.portal)
        migrate_events(self.portal)

        # assertions
        cat = self.catalog
        at_contents = cat(object_provides='Products.ATContentTypes'
                          '.interfaces.IATContentType')
        dx_contents = cat(object_provides='plone.dexterity'
                          '.interfaces.IDexterityContent')
        self.assertEqual(len(at_contents), 0)
        self.assertEqual(len(dx_contents), 11)
