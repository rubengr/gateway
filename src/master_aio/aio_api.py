# Copyright (C) 2016 OpenMotics BVBA
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
Contains the definition of the AIO API
"""

from aio_command import AIOCommandSpec, ByteField, WordField, ByteArrayField


class AIOAPI(object):

    @staticmethod
    def basic_action():
        """ Basic action spec """
        return AIOCommandSpec('BA',
                              [ByteField('type'), ByteField('action'), WordField('device_nr'), WordField('extra_parameter')],
                              [ByteField('type'), ByteField('action'), WordField('device_nr'), WordField('extra_parameter')])

    @staticmethod
    def event_information():
        """ Event information """
        return AIOCommandSpec('EV',
                              [],  # No request, only a response
                              [ByteField('type'), ByteField('action'), WordField('device_nr'), ByteArrayField('data', 4)])
