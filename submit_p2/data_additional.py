#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OpenStreetMap Sample Project Data Wrangling with MongoDB
This program transforms the shape of the OSM data into a list of dictionaries, and save the data as a JSON file.
It writes Japanese characters properly into the output file.

The transformation of the data includes the following things:
- it processes only 2 type of top level tags: "node" and "way".
- all attributes of "node" and "way" are turned into regular key/value pairs, except:
    - attributes in the CREATED array are added under a key "created".
    - attributes for latitude and longitude are added to a "pos" array as float numbers.
- if second level tag "k" value contains problematic characters, it is ignored.
- if second level tag "k" value starts with "addr:", it is added to a dictionary "address".
- if second level tag "k" value does not start with "addr:", but contains ":", the program processes it same as any other tag.
- if there is a second ":" that separates the type/direction of a street, the tag is ignored.
- for "way" specifically:
  <nd ref="305896090"/>
  <nd ref="1719825889"/>
are turned into 
"node_refs": ["305896090", "1719825889"]
- it converts full-width numbers and encircled numbers into half-width characters.
- it cleans address values.
  - remove problematic charctes like "yes", "(Kyoto)", and ";京都府道".
  - "city" should only contain "***市(city)". If it contains "***区(ward)", that part is moved to "street" value.
  - remove hyphen in "postcode". 123-4567 is turned into 1234567.
  - if "street" or "housenumber" contains phonenubmer or postcode, those values are moved to the right places.


"""


import xml.etree.ElementTree as ET
import pprint
import re
import codecs
import json
import string
import unicodedata

lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n\s　]')
addr = re.compile(r'addr:')
addr_problemchars = re.compile(r'\((.)*\)|yes') # problematic characters for address values (parenthesized characters and "yes")
addr_semicolon = re.compile(r';(.)*$') # separated characters by ";"
addr_space = re.compile(r'[\s　]') # whitespace
re_postcode = re.compile(r'^([0-9]{3}-[0-9]{4}$)') # postcode with hyphen
re_phonenumber = re.compile(r'(^(0[0-9]{2}-[0-9]{3}-[0-9]{4}$)|^(81\s[0-9]+$))') # phonenumber
re_city = re.compile(u"[^府]+市") # city
re_ward = re.compile(u"[^市]+区(.)*") # ward　

#chars = re.compile(u"[一-龥ぁ-んァ-ン0-9０-９a-zA-Z]*")
#wrong_housenumber = re.compile(r'([0-9]{3}-[0-9]{3}-[0-9]{4}|[0-9]{3}-[0-9]{4}|81\s[0-9]+$)')

CREATED = [ "version", "changeset", "timestamp", "user", "uid"]

def shape_element(element):
    # process only "node" and "way" top-level tags
    if element.tag == "node" or element.tag == "way" :
        node = {}
        lat = None
        lon = None
        node["type"] = element.tag

        for atr in element.attrib:
            # attributes in the CREATED array are added under a key "created"
            if atr in CREATED:
                if not node.has_key("created"):
                    node["created"] = {}
                # converts full-width characters and encircled numbers into half-width characters
                node["created"][atr] = unicodedata.normalize('NFKC', unicode(element.get(atr)))

            # latitude and longitude are added to a "pos" array as float numbers
            elif atr == "lat" or atr == "lon":
                if atr == "lat":
                    lat = element.get(atr)
                elif atr == "lon":
                    lon = element.get(atr)
                if lat and lon:
                    node["pos"] = [float(lat), float(lon)]

            # other tags are turned into regular key/value pairs        
            else:
                # converts full-width numbers and encircled numbers into half-width ones
                node[atr] = unicodedata.normalize('NFKC', unicode(element.get(atr)))
                        
            # process second-level tags
            for tag in element.iter("tag"):
                tk = tag.get("k")
                ad = addr.match(tk)
                tagv = tag.get("v")
                # ignores if "k" value contains problematic characters
                if problemchars.search(tk):
                    pass
                elif ad: # starts with "addr:"
                    # extracts the key under address
                    ad_cont = tk[5:]
                    # ignores if there is a second ":" 
                    if lower_colon.search(ad_cont):
                        pass
                    # add to a dictionary "address"
                    else:
                        if not node.has_key("address"):
                            node["address"] = {}
                        # full-width/encircled numbers are turned into half-width
                        node["address"][ad_cont] = unicodedata.normalize('NFKC', unicode(tagv))
                else: # does not start with "addr:"
                    if tk == "type": # if "k" = "type", modify the key to "type_m"
                        node["type_m"] = unicodedata.normalize('NFKC', unicode(tagv))
                    else:
                        node[tk] = unicodedata.normalize('NFKC', unicode(tagv))

                    
        ## clean address values
        if node.has_key("address"):
            ## focus five address keys
            address_key = ["city", "street", "housenumber", "housename", "postcode"]
            
            for key in address_key:
                if node["address"].has_key(key):
                    text = node["address"][key]
                    problem_chars = addr_problemchars.search(text)
                    semi_chars = addr_semicolon.search(text)
                    space_chars = addr_space.search(text)
                    
                    ## remove parenthesized characters, "yes", separeted characters by ";", and whitespaces
                    if problem_chars:
                        pc = problem_chars.group()
                        text = text.replace(pc, "")
                        node["address"][key] = text
                    if semi_chars:
                        sc = semi_chars.group()
                        text = text.replace(sc, "")
                        node["address"][key] = text
                    if space_chars:
                        spc = space_chars.group()
                        text = text.replace(spc, "")
                        node["address"][key] = text
                        

                    ## "city" value only contains "city(***市)" 
                    if key == "city":
                        city_chars = re_city.search(text)
                        ward_chars = re_ward.search(text)
                        if city_chars:
                            text = city_chars.group()
                            node["address"][key] = text
                        else:
                            node["address"][key] = ""

                        ## if "city" value contains "ward(***区)", that part is moved to "street" value 
                        if ward_chars:
                            text = ward_chars.group()
                            if node["address"].has_key("street"):
                                node["address"]["street"] = text + node["address"]["street"]
                            else:
                                node["address"]["street"] = text

                    ## remove hyphen from "postcode"
                    if key == "postcode":
                        wrong_post = re_postcode.search(text)
                        if wrong_post:
                            node["address"][key] = text[0:3] + text[4:8]
                                
                    ## solve confused "housenumber"/"street" problem 
                    if key == "housenumber" or key == "street":
                        phonenum = re_phonenumber.search(text)
                        postnum = re_postcode.search(text)
                        ## phonenumber goes to "phone" value in "created" dictionary
                        if phonenum:
                            if not node["created"].has_key("phone"):
                                node["created"]["phone"] = text
                                node["address"][key] = ""
                        ## postcode goes to "postcode" value in "address" dictionary
                        elif postnum:
                            if not node["address"].has_key("postcode"):
                                node["address"]["postcode"] = text[0:3] + text[4:8]
                                node["address"][key] = ""    
                
                else:
                    pass

            """
            for development use  
            """
            """
            for key in address_key:
                if node["address"].has_key(key):
                    print key, node["address"][key]
                else:
                    print key, " "
            print ""
            """
            """
            """

        ## "ref"s are added to list "node_refs"
        if element.tag == "way":
            for tag in element.iter("nd"):
                if not node.has_key("node_refs"):
                    node["node_refs"] = []
                node["node_refs"].append(tag.get("ref"))


        return node
    else:
        return None


def process_map(file_in, pretty = False):
    file_out = "{0}.json".format(file_in)
    data = []
    with codecs.open(file_out, "w", 'utf-8') as fo:
        for _, element in ET.iterparse(file_in):
            el = shape_element(element)
            if el:
                data.append(el)
                # added "ensure_ascii=False"
                if pretty:
                    fo.write(json.dumps(el, indent=2, ensure_ascii=False)+"\n")
                else:
                    fo.write(json.dumps(el, ensure_ascii=False) + "\n")
    return data

def test():
    # NOTE: if you are running this code on your computer, with a larger dataset, 
    # call the process_map procedure with pretty=False. The pretty=True option adds 
    # additional spaces to the output, making it significantly larger.
    data = process_map('kyoto_japan.osm', False)

if __name__ == "__main__":
    test()
