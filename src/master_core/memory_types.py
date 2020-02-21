# Copyright (C) 2019 OpenMotics BV
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Contains memory (field) types
"""
import inspect
import ujson as json
import logging
import types
from threading import Lock
from ioc import Inject, INJECTED

logger = logging.getLogger("openmotics")


class MemoryModelDefinition(object):
    """
    Represents a model definition
    """

    # TODO: Accept `None` and convert it to e.g. 255 and vice versa
    # TODO: Add (id) limits so we can't read memory we shouldn't read

    _cache_fields = {}
    _cache_addresses = {}
    _cache_lock = Lock()

    @Inject
    def __init__(self, id, memory_files=INJECTED):
        self.id = id
        self._memory_files = memory_files
        self._fields = []
        self._loaded_fields = set()
        self._relations = []
        self._relations_cache = {}
        self._compositions = []
        address_cache = self.__class__._get_address_cache(self.id)
        for field_name, field_type in self.__class__._get_field_dict().iteritems():
            setattr(self, '_{0}'.format(field_name), MemoryFieldContainer(field_type,
                                                                          address_cache[field_name],
                                                                          self._memory_files))
            self._add_property(field_name)
            self._fields.append(field_name)
        for field_name, relation in self.__class__._get_relational_fields().iteritems():
            setattr(self, '_{0}'.format(field_name), relation)
            self._add_relation(field_name)
            self._relations.append(field_name)
        for field_name, composition in self.__class__._get_composite_fields().iteritems():
            setattr(self, '_{0}'.format(field_name), CompositionContainer(composition,
                                                                          composition._field._length * 8,
                                                                          MemoryFieldContainer(composition._field,
                                                                                               composition._field.get_address(self.id),
                                                                                               self._memory_files)))
            self._add_composition(field_name)
            self._compositions.append(field_name)

    def __str__(self):
        return str(json.dumps(self.serialize(), indent=4))

    def serialize(self):
        data = {}
        if self.id is not None:
            data['id'] = self.id
        for field_name in self._fields:
            data[field_name] = getattr(self, field_name)
        for field_name in self._compositions:
            data[field_name] = getattr(self, field_name).serialize()
        return data

    def _add_property(self, field_name):
        setattr(self.__class__, field_name, property(lambda s: s._get_property(field_name),
                                                     lambda s, v: s._set_property(field_name, v)))

    def _get_property(self, field_name):
        self._loaded_fields.add(field_name)
        field = getattr(self, '_{0}'.format(field_name))
        return field.decode()

    def _set_property(self, field_name, value):
        self._loaded_fields.add(field_name)
        field = getattr(self, '_{0}'.format(field_name))
        field.encode(value)

    def _add_relation(self, field_name):
        setattr(self.__class__, field_name, property(lambda s: s._get_relation(field_name)))

    def _get_relation(self, field_name):
        if field_name not in self._relations_cache:
            relation = getattr(self, '_{0}'.format(field_name))
            self._relations_cache[field_name] = relation.yield_instance(self.id)
        return self._relations_cache[field_name]

    def _add_composition(self, field_name):
        setattr(self.__class__, field_name, property(lambda s: s._get_composition(field_name)))

    def _get_composition(self, field_name):
        self._loaded_fields.add(field_name)
        return getattr(self, '_{0}'.format(field_name))

    def save(self):
        for field_name in self._loaded_fields:
            field_container = getattr(self, '_{0}'.format(field_name))
            field_container.save()

    @classmethod
    def deserialize(cls, data):
        instance_id = data['id']
        instance = cls(instance_id)
        for field_name, value in data.iteritems():
            if field_name == 'id':
                pass
            elif field_name in instance._fields:
                setattr(instance, field_name, value)
            elif field_name in instance._relations:
                relation = getattr(instance, '_{0}'.format(field_name))
                instance._relations_cache[field_name] = relation.instance_type.deserialize(value)
            elif field_name in instance._compositions:
                composition = getattr(instance, '_{0}'.format(field_name))
                composition._load(value)
            else:
                raise ValueError('Unknown field: {0}', field_name)
        return instance

    @classmethod
    def _get_fields(cls):
        """ Get the fields defined by an EepromModel child. """
        if cls.__name__ not in MemoryModelDefinition._cache_fields:
            MemoryModelDefinition._cache_fields[cls.__name__] = {'fields': inspect.getmembers(cls, lambda f: isinstance(f, MemoryField)),
                                                                 'relations': inspect.getmembers(cls, lambda f: isinstance(f, MemoryRelation)),
                                                                 'compositions': inspect.getmembers(cls, lambda f: isinstance(f, CompositeMemoryModelDefinition))}
        return MemoryModelDefinition._cache_fields[cls.__name__]

    @classmethod
    def _get_field_dict(cls):
        """
        Get a dict from the field name to the field type for each field defined by model
        """
        class_field_dict = {}
        for name, field_type in cls._get_fields()['fields']:
            class_field_dict[name] = field_type
        return class_field_dict

    @classmethod
    def _get_relational_fields(cls):
        """
        Gets a dict of all relational fields
        """
        relation_field_dict = {}
        for name, field_type in cls._get_fields()['relations']:
            relation_field_dict[name] = field_type
        return relation_field_dict

    @classmethod
    def _get_composite_fields(cls):
        """
        Gets a dict of all composite fields
        """
        composite_field_dict = {}
        for name, field_type in cls._get_fields()['compositions']:
            composite_field_dict[name] = field_type
        return composite_field_dict

    @classmethod
    def _get_address_cache(cls, id):
        if cls.__name__ in MemoryModelDefinition._cache_addresses:
            class_cache = MemoryModelDefinition._cache_addresses[cls.__name__]
        else:
            with MemoryModelDefinition._cache_lock:
                class_cache = MemoryModelDefinition._cache_addresses.setdefault(cls.__name__, {})
        if id in class_cache:
            return class_cache[id]
        with MemoryModelDefinition._cache_lock:
            cache = {}
            for field_name, field_type in cls._get_fields()['fields']:
                cache[field_name] = field_type.get_address(id)
            class_cache[id] = cache
        return cache


class GlobalMemoryModelDefinition(MemoryModelDefinition):
    """
    Represents a model definition
    """

    def __init__(self):
        super(GlobalMemoryModelDefinition, self).__init__(None)


class MemoryFieldContainer(object):
    """
    This object holds the MemoryField and the data.
    """

    def __init__(self, memory_field, memory_address, memory_files):
        """
        :type memory_field: master_core.memory_types.MemoryField
        :type memory_address: master_core.memory_types.MemoryAddress
        """
        self._memory_field = memory_field
        self._memory_address = memory_address
        self._memory_files = memory_files
        self._data = None

    def _read_data(self):
        self._data = self._memory_files[self._memory_address.memory_type].read([self._memory_address])[self._memory_address]

    def encode(self, value):
        """ Encodes changes a high-level value such as a string or large integer into a memory byte array (array of 0 <= x <= 255) """
        self._data = self._memory_field.encode(value)

    def decode(self):
        """ Decodes a memory byte array (array of 0 <= x <= 255) into a high-level valuye shuch as a string or large integer """
        if self._data is None:
            self._read_data()
        return self._memory_field.decode(self._data)

    def save(self):
        self._memory_files[self._memory_address.memory_type].write({self._memory_address: self._data})


class MemoryField(object):
    """
    Defines a memory and provides encode/decode functions to convert this memory type from and to its memory representation.
    Besides these functions, the memory type also contains the address or address generator (in case the model has an id).
    """

    def __init__(self, memory_type, address_spec, length):
        """
        Create an instance of an MemoryDataType with an address or an address generator.

        :type address_spec: (int, int) or (int) => (int, int)
        """
        self._address_tuple = None
        self._address_generator = None
        self._memory_type = memory_type
        self._length = length

        self._data = None

        if isinstance(address_spec, types.TupleType):
            self._address_tuple = address_spec
        elif isinstance(address_spec, types.FunctionType):
            args = inspect.getargspec(address_spec).args
            if len(args) == 1:
                self._address_generator = address_spec
            else:
                raise TypeError('Parameter `address_spec` should be a function that takes an id and returns the same tuple.')
        else:
            raise TypeError('Parameter `address_spec` should be a tuple (page, offset) or a function that takes an id and returns the same tuple.')

    def get_address(self, id):
        """
        Calculate the address for this field.

        :rtype: master_core.memory_types.MemoryAddress
        """
        if id is None:
            if self._address_tuple is None:
                raise TypeError('MemoryField expects an id')
            page, offset = self._address_tuple
        else:
            if self._address_generator is None:
                raise TypeError('MemoryField did not expect an id')
            page, offset = self._address_generator(id)
        return MemoryAddress(self._memory_type, page, offset, self._length)

    def encode(self, data):
        """ Encodes changes a high-level value such as a string or large integer into a memory byte array (array of 0 <= x <= 255) """
        raise NotImplementedError()

    def decode(self, value):
        """ Decodes a memory byte array (array of 0 <= x <= 255) into a high-level valuye shuch as a string or large integer """
        raise NotImplementedError()


class MemoryStringField(MemoryField):
    def __init__(self, memory_type, address_spec, length):
        super(MemoryStringField, self).__init__(memory_type, address_spec, length)

    def encode(self, value):
        if len(value) > self._length:
            raise ValueError('Value {0} should be a string of {1} characters'.format(value, self._length))
        data = []
        for char in value:
            data.append(ord(char))
        data += [255] * (len(data) - self._length)
        return data

    def decode(self, data):
        while len(data) >= 1 and data[-1] in [0, 255]:
            data.pop()
        return ''.join([str(chr(item)) if 32 <= item <= 126 else ' ' for item in data])


class MemoryByteField(MemoryField):
    def __init__(self, memory_type, address_spec):
        super(MemoryByteField, self).__init__(memory_type, address_spec, 1)

    @classmethod
    def encode(cls, value):
        if not (0 <= value <= 255):
            raise ValueError('Value {0} out of limits: 0 <= value <= 255'.format(value))
        return [value]

    @classmethod
    def decode(cls, data):
        return data[0]


class MemoryWordField(MemoryField):
    def __init__(self, memory_type, address_spec):
        super(MemoryWordField, self).__init__(memory_type, address_spec, 2)

    @classmethod
    def encode(cls, value):
        max_value = 2 ** 16 -1
        if not (0 <= value <= max_value):
            raise ValueError('Value {0} out of limits: 0 <= value <= {1}'.format(value, max_value))
        return [value / 256, value % 256]

    @classmethod
    def decode(cls, data):
        return (data[0] * 256) + data[1]


class Memory3BytesField(MemoryField):
    def __init__(self, memory_type, address_spec):
        super(Memory3BytesField, self).__init__(memory_type, address_spec, 3)

    @classmethod
    def encode(cls, value):
        max_value = 2 ** 24 - 1
        if not (0 <= value < max_value):
            raise ValueError('Value {0} out of limits: 0 <= value <= {1}'.format(value, max_value))
        ms_byte = value / (256 * 256)
        rest = value % (256 * 256)
        return [ms_byte, rest / 256, rest % 256]

    @classmethod
    def decode(cls, data):
        return (data[0] * 256 * 266) + (data[1] * 256) + data[2]


class MemoryByteArrayField(MemoryField):
    def __init__(self, memory_type, address_spec, length):
        super(MemoryByteArrayField, self).__init__(memory_type, address_spec, length)

    def encode(self, value):
        if len(value) != self._length:
            raise ValueError('Value {0} should be an array of {1} items with 0 <= item <= 255'.format(value, self._length))
        for item in value:
            if not (0 <= item <= 255):
                raise ValueError('One of the items {0} in value is out of limits: 0 <= item <= 255'.format(value))
        return value

    def decode(self, data):
        return data


class MemoryBasicActionField(MemoryByteArrayField):
    def __init__(self, memory_type, address_spec):
        super(MemoryBasicActionField, self).__init__(memory_type, address_spec, 6)

    def encode(self, value):
        from master_core.basic_action import BasicAction  # Prevent circular import

        if not isinstance(value, BasicAction):
            raise ValueError('Value should be a BasicAction')
        return value.encode()

    def decode(self, data):
        from master_core.basic_action import BasicAction  # Prevent circular import

        return BasicAction.decode(data)


class MemoryAddressField(MemoryField):
    def __init__(self, memory_type, address_spec, length=4):
        super(MemoryAddressField, self).__init__(memory_type, address_spec, length)

    def encode(self, value):
        example = '.'.join(['ID{0}'.format(i) for i in xrange(self._length - 1, -1, -1)])
        error_message = 'Value should be a string in the format of {0}, where 0 <= IDx <= 255'.format(example)
        parts = str(value).split('.')
        if len(parts) != self._length:
            raise ValueError(error_message)
        data = []
        for part in parts:
            try:
                part = int(part)
            except ValueError:
                raise ValueError(error_message)
            if not (0 <= part <= 255):
                raise ValueError(error_message)
            data.append(part)
        return data

    def decode(self, data):
        return '.'.join('{0:03}'.format(item) for item in data)


class MemoryVersionField(MemoryAddressField):
    def __init__(self, memory_type, address_spec):
        super(MemoryVersionField, self).__init__(memory_type, address_spec, length=3)

    def decode(self, data):
        return '.'.join(str(item) for item in data)


class MemoryRelation(object):
    def __init__(self, instance_type, id_spec):
        """
        :type instance_type: type
        """
        self.instance_type = instance_type
        self._id_spec = id_spec

    def yield_instance(self, own_id):
        return self.instance_type(self._id_spec(own_id))

    def serialize(self):
        raise NotImplementedError()

    def save(self):
        raise NotImplementedError()


class MemoryAddress(object):
    """ Represents an address in the EEPROM/FRAM. Has a memory type, page, offset and length """

    def __init__(self, memory_type, page, offset, length):
        self.memory_type = memory_type
        self.page = page
        self.offset = offset
        self.length = length

    def __hash__(self):
        return ord(self.memory_type) + self.page * 256 + self.offset * 256 * 256 + self.length * 256 * 256 * 256

    def __str__(self):
        return 'Address({0}{1}, {2}, {3})'.format(self.memory_type, self.page, self.offset, self.length)

    def __eq__(self, other):
        if not isinstance(other, MemoryAddress):
            return False
        return hash(self) == hash(other)


class CompositeField(object):
    def decompose(self, value):
        """ Decomposes a value out of the given composite value """
        raise NotImplementedError()

    def compose(self, base_value, value, composition_width):
        """ Composes a value onto a base (current) value """
        raise NotImplementedError()


class CompositeNumberField(CompositeField):
    def __init__(self, start_bit, width, value_offset=0, max_value=None):
        super(CompositeNumberField, self).__init__()
        self._mask = 2 ** width - 1 << start_bit
        self._start_bit = start_bit
        if max_value is None:
            self._max_value = 2 ** width - 1
        else:
            self._max_value = max_value
        self._value_offset = value_offset

    def decompose(self, value):
        return self._decompose(value)

    def _decompose(self, value):
        value = ((value & self._mask) >> self._start_bit) - self._value_offset
        if self._max_value is None or 0 <= value <= self._max_value:
            return value
        return None

    def compose(self, current_composition, value, composition_width):
        return self._compose(current_composition, value, composition_width)

    def _compose(self, current_composition, value, composition_width):
        current_value = self._decompose(current_composition)
        if value == current_value:
            return current_composition
        if self._max_value is not None and not (0 <= value <= self._max_value):
            raise ValueError('Value out of limits: 0 <= value <= {0}'.format(self._max_value))
        value = ((value + self._value_offset) << self._start_bit) & self._mask
        current_composition = current_composition & ~self._mask & (2 ** composition_width - 1)
        return current_composition | value


class CompositeBitField(CompositeNumberField):
    def __init__(self, bit):
        super(CompositeBitField, self).__init__(bit, 1)

    def decompose(self, value):
        value = super(CompositeBitField, self).decompose(value)
        return value == 1

    def compose(self, current_composition, value, composition_width):
        value = 1 if value else 0
        return super(CompositeBitField, self)._compose(current_composition, value, composition_width)


class CompositeMemoryModelDefinition(object):
    """
    Represents a composite model definition. This class (only) holds composite fields
    """

    _cache_fields = {}

    def __init__(self, field):
        self._field = field

    @classmethod
    def _get_field_names(cls):
        """ Get the field names defined by an MemoryModel child. """
        if cls.__name__ not in CompositeMemoryModelDefinition._cache_fields:
            CompositeMemoryModelDefinition._cache_fields[cls.__name__] = [entry[0] for entry in inspect.getmembers(cls, lambda f: isinstance(f, CompositeField))]
        return CompositeMemoryModelDefinition._cache_fields[cls.__name__]


class CompositionContainer(object):
    """
    This object holds the MemoryField and the data.
    """

    def __init__(self, composite_definition, composition_width, field_container):
        """
        :type composite_definition: master_core.memory_types.CompositeMemoryModelDefinition
        :type composition_width: int
        :type field_container: master_core.memory_types.MemoryFieldContainer
        """
        self._composite_definition = composite_definition
        self._composition_width = composition_width
        self._field_container = field_container
        self._fields = []
        for field_name in self._composite_definition.__class__._get_field_names():
            self._add_property(field_name)
            self._fields.append(field_name)

    def _add_property(self, field_name):
        setattr(self.__class__, field_name, property(lambda s: s._get_property(field_name),
                                                     lambda s, v: s._set_property(field_name, v)))

    def _get_property(self, field_name):
        field = getattr(self._composite_definition, field_name)
        return field.decompose(self._field_container.decode())

    def _set_property(self, field_name, value):
        field = getattr(self._composite_definition, field_name)
        current_composition = self._field_container.decode()
        self._field_container.encode(field.compose(current_composition, value, self._composition_width))

    def _load(self, data):
        for field_name, value in data.iteritems():
            if field_name == 'id':
                pass
            elif field_name in self._fields:
                self._set_property(field_name, value)
            else:
                raise ValueError('Unknown field: {0}', field_name)

    def serialize(self):
        data = {}
        for field_name in self._fields:
            data[field_name] = self._get_property(field_name)
        return data

    def save(self):
        self._field_container.save()
