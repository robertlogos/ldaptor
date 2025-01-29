Ldaptor
=======

Repo original: https://github.com/twisted/ldaptor


Instalar las dependencias::

    pip install twisted pyOpenSSL service-identity

Configurar el endpoint del proxy en **proxy.py**::

     proxiedEndpointStr = 'tcp:host=localhost:port=389'


Ejecutar el proxy::

    python proxy.py

La sección con la lógica clave se encuentra en **ldaptor/_encoder.py**:

.. code-block:: python

    if type(value).__name__=='BEROctetString':
        bstr = value.value
        if (len(bstr)>3) and (bstr[:3] == b'cn='):
            value.value = bstr.replace(b'\xc3\x84N', b'\xc3\x91') #Letra Ñ

Se puede usar el **Dockerfile** contenerizar el proxy mediante docker o podman::

    docker build -t ldaptor .
    docker run -p 10389:10389 ldaptor






