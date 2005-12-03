import sets, random, sha, base64
from twisted.internet import defer
from twisted.python.util import InsensitiveDict
from ldaptor import interfaces, attributeset, delta
from ldaptor.protocols.ldap import distinguishedname, ldif, ldaperrors

def sshaDigest(passphrase, salt=None):
    if salt is None:
        salt = ''
        for i in range(8):
            salt += chr(random.randint(0, 255))

    s = sha.sha()
    s.update(passphrase)
    s.update(salt)
    encoded = base64.encodestring(s.digest()+salt).rstrip()
    crypt = '{SSHA}' + encoded
    return crypt

class BaseLDAPEntry(object):
    __implements__ = (interfaces.ILDAPEntry,)
    dn = None

    def __init__(self, dn, attributes={}):
	"""

	Initialize the object.

	@param dn: Distinguished Name of the object, as a string.

	@param attributes: Attributes of the object. A dictionary of
	attribute types to list of attribute values.

	"""
	self._attributes=InsensitiveDict()
	self.dn = distinguishedname.DistinguishedName(dn)

	for k,vs in attributes.items():
            if k not in self._attributes:
                self._attributes[k] = []
            self._attributes[k].extend(vs)

        for k,vs in self._attributes.items():
            self._attributes[k] = self.buildAttributeSet(k, vs)

    def buildAttributeSet(self, key, values):
        return attributeset.LDAPAttributeSet(key, values)

    def __getitem__(self, key):
	return self._attributes[key]

    def get(self, key, default=None):
	return self._attributes.get(key, default)

    def has_key(self, key):
	return key in self._attributes

    def __contains__(self, key):
        return self.has_key(key)

    def keys(self):
	return self._attributes.keys()

    def items(self):
	return self._attributes.items()

    def __str__(self):
	a=[]

	objectClasses = list(self.get('objectClass', []))
	objectClasses.sort()
	a.append(('objectClass', objectClasses))

	l=list(self.items())
	l.sort()
	for key, values in l:
	    if key.lower() != 'objectclass':
                vs = list(values)
                vs.sort()
		a.append((key, vs))
	return ldif.asLDIF(self.dn, a)

    def __eq__(self, other):
	if not isinstance(other, self.__class__):
	    return 0
	if self.dn != other.dn:
	    return 0

	my=self.keys()
	my.sort()
	its=other.keys()
	its.sort()
	if my!=its:
	    return 0
	for key in my:
	    myAttr=self[key]
	    itsAttr=other[key]
	    if myAttr!=itsAttr:
		return 0
	return 1

    def __ne__(self, other):
	return not self==other

    def __len__(self):
	return len(self.keys())

    def __nonzero__(self):
        return True

    def __repr__(self):
	x={}
	for key in self.keys():
	    x[key]=self[key]
	keys=self.keys()
	keys.sort()
	a=[]
	for key in keys:
	    a.append('%s: %s' % (repr(key), repr(list(self[key]))))
	attributes=', '.join(a)
	return '%s(%s, {%s})' % (
	    self.__class__.__name__,
	    repr(str(self.dn)),
            attributes)

    def diff(self, other):
        """
        Compute differences between this and another LDAP entry.

        @param other: An LDAPEntry to compare to.

        @return: None if equal, otherwise a ModifyOp that would make
        this entry look like other.
        """
        assert self.dn == other.dn
        if self == other:
            return None

        r = []

        myKeys = sets.Set(self.keys())
        otherKeys = sets.Set(other.keys())

        addedKeys = list(otherKeys - myKeys)
        addedKeys.sort() # for reproducability only
        for added in addedKeys:
            r.append(delta.Add(added, other[added]))

        deletedKeys = list(myKeys - otherKeys)
        deletedKeys.sort() # for reproducability only
        for deleted in deletedKeys:
            r.append(delta.Delete(deleted, self[deleted]))

        sharedKeys = list(myKeys & otherKeys)
        sharedKeys.sort() # for reproducability only
        for shared in sharedKeys:

            addedValues = list(other[shared] - self[shared])
            if addedValues:
                addedValues.sort() # for reproducability only
                r.append(delta.Add(shared, addedValues))

            deletedValues = list(self[shared] - other[shared])
            if deletedValues:
                deletedValues.sort() # for reproducability only
                r.append(delta.Delete(shared, deletedValues))

        return delta.ModifyOp(dn=self.dn, modifications=r)

    def bind(self, password):
        return defer.maybeDeferred(self._bind, password)

    def _bind(self, password):
        for digest in self.get('userPassword', ()):
            if digest.startswith('{SSHA}'):
                raw = base64.decodestring(digest[len('{SSHA}'):])
                salt = raw[20:]
                got = sshaDigest(password, salt)
                if got == digest:
                    return self
        raise ldaperrors.LDAPInvalidCredentials
        
    def hasMember(self, dn):
        for memberDN in self.get('member', []):
            if memberDN == dn:
                return True
        return False

class EditableLDAPEntry(BaseLDAPEntry):
    __implements__ = (interfaces.IEditableLDAPEntry,)

    def __setitem__(self, key, value):
	new=self.buildAttributeSet(key, value)
        self._attributes[key] = new

    def __delitem__(self, key):
        del self._attributes[key]

    def undo(self):
        raise NotImplementedError

    def commit(self):
        raise NotImplementedError

    def move(self, newDN):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    def setPassword(self, newPasswd, salt=None):
        crypt = sshaDigest(newPasswd, salt)
        self['userPassword'] = [crypt]

class DiffTreeMixin(object):
    def _diffTree_gotMyChildren(self, myChildren, other, result):
        d = other.children()
        d.addCallback(self._diffTree_gotBothChildren, myChildren, other, result)
        return d

    def _diffTree_gotBothChildren(self,
                                  otherChildren,
                                  myChildren,
                                  other,
                                  result):
        def rdnToChild(rdn, l):
            r = [x for x in l if x.dn.split()[0] == rdn]
            assert len(r) == 1
            return r[0]

        my = sets.Set([x.dn.split()[0] for x in myChildren])
        his = sets.Set([x.dn.split()[0] for x in otherChildren])

        # differences in common children
        commonRDN = list(my & his)
        commonRDN.sort() # for reproducability only
        d = self._diffTree_commonChildren([
            (rdnToChild(rdn, myChildren), rdnToChild(rdn, otherChildren))
            for rdn in commonRDN
            ], result)

        # added children
        addedRDN = list(his - my)
        addedRDN.sort() # for reproducability only
        d2 = self._diffTree_addedChildren([
            rdnToChild(rdn, otherChildren)
            for rdn in addedRDN
            ], result)
        d.addCallback(lambda _: d2)

        # deleted children
        deletedRDN = list(my - his)
        deletedRDN.sort() # for reproducability only
        d3 = self._diffTree_deletedChildren([
            rdnToChild(rdn, myChildren)
            for rdn in deletedRDN
            ], result)
        d.addCallback(lambda _: d3)

        return d

    def _diffTree_commonChildren(self, children, result):
        if not children:
            return defer.succeed(result)
        first, rest = children[0], children[1:]
        a, b = first
        d = a.diffTree(b, result)
        d.addCallback(lambda _: self._diffTree_commonChildren(rest, result))
        return d

    def _diffTree_addedChildren(self, children, result):
        if not children:
            return result
        first, rest = children[0], children[1:]

        d = first.subtree()
        def _gotSubtree(l, result):
            for c in l:
                o = delta.AddOp(c)
                result.append(o)
            return result
        d.addCallback(_gotSubtree, result)

        d.addCallback(lambda _: self._diffTree_addedChildren(rest, result))
        return d

    def _diffTree_deletedChildren(self, children, result):
        if not children:
            return result
        first, rest = children[0], children[1:]

        d = first.subtree()
        def _gotSubtree(l, result):
            l.reverse() # remove children before their parent
            for c in l:
                o = delta.DeleteOp(c)
                result.append(o)
            return result
        d.addCallback(_gotSubtree, result)

        d.addCallback(lambda _: self._diffTree_deletedChildren(rest, result))
        return d

    def diffTree(self, other, result=None):
        assert self.dn == other.dn, \
               ("diffTree arguments must refer to same LDAP tree:"
                "%r != %r" % (str(self.dn), str(other.dn))
                )
        if result is None:
            result = []

        # differences in root
        rootDiff = self.diff(other)
        if rootDiff is not None:
            result.append(rootDiff)

        d = self.children()
        d.addCallback(self._diffTree_gotMyChildren, other, result)

        return d
