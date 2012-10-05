'''
Tests for the outputs module.

Created on Sep 22, 2012

@author: fryckbos
'''
import unittest
import time

from outputs import OutputStatus

class OutputStatusTest(unittest.TestCase):
    """ Tests for OutputStatus. """

    def test_update(self):
        """ Test for partial_update and full_update"""
        outputs = [
                   { 'output_nr' : 1, 'name' : 'light1', 'floor_level' : 1, 'light' : 1,
                     'type' : 'D', 'controller_out' : 1, 'timer' : 200, 'ctimer' : 200,
                     'max_power' : 1,'status' : 1, 'dimmer' : 10 },
                   { 'output_nr' : 2, 'name' : 'light2', 'floor_level' : 2, 'light' : 1,
                     'type' : 'D', 'controller_out' : 1, 'timer' : 200, 'ctimer' : 200,
                     'max_power' : 1,'status' : 0, 'dimmer' : 20 },
                   { 'output_nr' : 3, 'name' : 'light1', 'floor_level' : 1, 'light' : 0,
                     'type' : 'O', 'controller_out' : 1, 'timer' : 200, 'ctimer' : 200,
                     'max_power' : 1,'status' : 0, 'dimmer' : 0 }
                  ]
        status = OutputStatus(outputs, 1)
        
        status.partial_update([]) # Everything is off
        self.assertEquals(0, status.get_outputs()[0]['status'])
        self.assertEquals(10, status.get_outputs()[0]['dimmer'])
        self.assertEquals(0, status.get_outputs()[1]['status'])
        self.assertEquals(20, status.get_outputs()[1]['dimmer'])
        self.assertEquals(0, status.get_outputs()[2]['status'])
        self.assertEquals(0, status.get_outputs()[2]['dimmer'])
        
        status.partial_update([(3, 0), (2, 1)])
        self.assertEquals(0, status.get_outputs()[0]['status'])
        self.assertEquals(10, status.get_outputs()[0]['dimmer'])
        self.assertEquals(1, status.get_outputs()[1]['status'])
        self.assertEquals(1, status.get_outputs()[1]['dimmer'])
        self.assertEquals(1, status.get_outputs()[2]['status'])
        self.assertEquals(0, status.get_outputs()[2]['dimmer'])
    
        update = [
                   { 'output_nr' : 1, 'name' : 'light1', 'floor_level' : 1, 'light' : 1,
                     'type' : 'D', 'controller_out' : 1, 'timer' : 200, 'ctimer' : 200,
                     'max_power' : 1,'status' : 0, 'dimmer' : 50 },
                   { 'output_nr' : 2, 'name' : 'light2', 'floor_level' : 2, 'light' : 1,
                     'type' : 'D', 'controller_out' : 1, 'timer' : 200, 'ctimer' : 200,
                     'max_power' : 1,'status' : 0, 'dimmer' : 80 },
                   { 'output_nr' : 3, 'name' : 'light1', 'floor_level' : 1, 'light' : 0,
                     'type' : 'O', 'controller_out' : 1, 'timer' : 200, 'ctimer' : 200,
                     'max_power' : 1,'status' : 1, 'dimmer' : 0 }
                  ]
    
        status.full_update(update)
        self.assertEquals(0, status.get_outputs()[0]['status'])
        self.assertEquals(50, status.get_outputs()[0]['dimmer'])
        self.assertEquals(0, status.get_outputs()[1]['status'])
        self.assertEquals(80, status.get_outputs()[1]['dimmer'])
        self.assertEquals(1, status.get_outputs()[2]['status'])
        self.assertEquals(0, status.get_outputs()[2]['dimmer'])
    
    
    def test_should_refresh(self):
        """ Test for should_refresh. """
        status = OutputStatus([], 100)
        self.assertFalse(status.should_refresh())
        
        status = OutputStatus([], 0.001)
        time.sleep(0.01)
        self.assertTrue(status.should_refresh())

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()