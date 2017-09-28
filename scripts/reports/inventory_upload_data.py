
import json
import lmfdb.inventory_app.inventory_helpers as ih
import lmfdb.inventory_app.lmfdb_inventory as inv
import lmfdb.inventory_app.inventory_db_inplace as invip
import lmfdb.inventory_app.inventory_db_core as invc
import datetime

#TODO this should log to its own logger
#Routines to upload data from reports scan into inventory DB

MAX_SZ = 10000

def upload_from_files(db, master_file_name, list_file_name, fresh=False):
    """Upload an entire inventory. CLOBBERS CONTENT

        db -- LMFDB connection to inventory database
        master_file_name -- path to report tool database structure file
        list_file_name -- path to file containing list of all additional inventory info files
        fresh -- set to skip some syncing if this is a fresh or new upload
    """
    #For a complete upload is more logical to fill things in thing by thing
    #so we do all the db's first, then the collections and finish with the additional description

    decoder = json.JSONDecoder()
    structure_dat = decoder.decode(read_file(master_file_name))

    inv.log_dest.info("_____________________________________________________________________________________________")
    inv.log_dest.info("Processing autogenerated inventory")
    n_dbs = len(structure_dat.keys)
    progress_tracker = 0
    for DB_name in structure_dat:
        progress_tracker += 1
        inv.log_dest.info("Uploading " + DB_name+" ("+str(progress_tracker)+" of "+str(n_dbs)+')')
        _id = invc.set_db(db, DB_name, DB_name)

        for coll_name in structure_dat[DB_name]:
            inv.log_dest.info("    Uploading collection "+coll_name)
            coll_entry = invc.set_coll(db, _id['id'], coll_name, coll_name, '', '')

            try:
                scrape_date = dt.datetime.strptime(structure_dat[DB_name][coll_name]['scrape_date'], '%Y-%m-%d %H:%M:%S.%f')
            except:
                scrape_date = datetime.datetime(min)
            invc.set_coll_scrape_date(db, coll_entry['id'], scrape_date)

            orphaned_keys = upload_collection_structure(db, DB_name, coll_name, structure_dat, fresh=fresh)
            if len(orphaned_keys) != 0:
                with open('Orph_'+DB_name+'_'+coll_name+'.json', 'w') as file:
		    file.write(json.dumps(orphaned_keys))
		inv.log_dest.info("          Orphans written to Orph_"+ DB_name+'_'+coll_name+'.json')

    inv.log_dest.info("_____________________________________________________________________________________________")
    inv.log_dest.info("Processing additional inventory")
    file_list = read_list(list_file_name)
    last_db = ''
    progress_tracker = 0
    for file in file_list:
        data = decoder.decode(read_file(file))
        record_name = ih.get_description_key(file)
        DB_name = record_name[0]
        if DB_name != last_db:
            inv.log_dest.info("Uploading " + DB_name+" ("+str(progress_tracker)+" of <"+str(n_dbs)+')')
            last_db = DB_name
            progress_tracker += 1
        coll_name = record_name[1]
        inv.log_dest.info("    Uploading collection "+coll_name)

        upload_collection_description(db, DB_name, coll_name, data)

def upload_collection_from_files(db, db_name, coll_name, master_file_name, json_file_name, fresh=False):
    """Freshly upload inventory for a single collection. CLOBBERS CONTENT

        db -- LMFDB connection to inventory database
        db_name -- Name of database this collection is in
        coll_name -- Name of collection to upload
        master_file_name -- path to report tool database structure file
        json_file_name -- path to file containing additional inventory data
        fresh -- set to skip some syncing if this is a fresh or new upload
    """

    decoder = json.JSONDecoder()

    inv.log_dest.info("Uploading collection structure for "+coll_name)
    structure_data = decoder.decode(read_file(master_file_name))
    orphaned_keys = upload_collection_structure(db, db_name, coll_name, structure_data, fresh=fresh)

    inv.log_dest.info("Uploading collection description for "+coll_name)
    data = decoder.decode(read_file(json_file_name))
    upload_collection_description(db, db_name, coll_name, data)

def upload_collection_description(db, db_name, coll_name, data):
    """Upload the additional description

    db -- LMFDB connection to inventory database
    db_name -- Name of database this collection is in
    coll_name -- Name of collection to upload
    data -- additional data as json object for this collection
    """

    try:
        db_entry = invc.get_db_id(db, db_name)
        _c_id = invc.get_coll_id(db, db_entry['id'], coll_name)
        if not (db_entry['exist'] and _c_id['exist']):
            #All dbs/collections should have been added from the struc: if not is error
            inv.log_dest.error("Cannot add descriptions, db or collection not found")
            return
    except Exception as e:
        inv.log_dest.error("Failed to refresh collection "+str(e))

    try:
        split_data = extract_specials(data)

        #Insert the notes and info fields into the collection
        split_data[inv.STR_NOTES] = ih.blank_all_empty_fields(split_data[inv.STR_NOTES])
        inv.log_dest.debug(split_data[inv.STR_NOTES])
        split_data[inv.STR_INFO] = ih.blank_all_empty_fields(split_data[inv.STR_INFO])
        inv.log_dest.debug(split_data[inv.STR_INFO])
        _c_id = invc.set_coll(db, db_entry['id'], coll_name, coll_name, split_data[inv.STR_NOTES], split_data[inv.STR_INFO])

        for field in split_data['data']:
            dat = split_data['data'][field]
            if not ih.is_record_name(dat):
                inv.log_dest.info("            Processing "+field)
                invc.set_field(db, _c_id['id'], field, dat, type='human')
            else:
                inv.log_dest.info("            Processing record "+field)
                invc.set_record(db, _c_id['id'], {'hash':field, 'name':dat['name'], 'description':dat['description']}, type='human')
    except Exception as e:
        inv.log_dest.error("Failed to refresh collection "+str(e))

def upload_collection_structure(db, db_name, coll_name, structure_dat, fresh=False):
    """Upload the structure description for a single collection

    Any entered descriptions for keys which still exist are preserved.
    Removed or renamed keys will be returned for handling
    db -- LMFDB connection to inventory database
    db_name -- Name of database this collection is in
    coll_name -- Name of collection to upload
    structure_dat -- lmfdb db structure as json object
    """

    try:
        coll_entry = structure_dat[db_name][coll_name]
        db_entry = invc.get_db_id(db, db_name)
        if not db_entry['exist']:
            #All dbs should have been added from the struc: if not is error
            inv.log_dest.error("ERROR: No inventory DB entry "+ db_name)
            inv.log_dest.error("Cannot add descriptions")
            return

        _c_id = invc.get_coll_id(db, db_entry['id'], coll_name)
        if not _c_id['exist']:
	    #Collection doesn't exist, create it
            _c_id = invc.set_coll(db, db_entry['id'], coll_name, coll_name,  '', '')
        else:
	    #Delete existing auto-table entries
           delete_collection_data(db, _c_id['id'], tbl='auto')
        try:
            scrape_date = dt.datetime.strptime(structure_dat[db_name][coll_name]['scrape_date'], '%Y-%m-%d %H:%M:%S.%f')
        except:
            scrape_date = datetime.datetime(min)
        invc.set_coll_scrape_date(db, _c_id['id'], scrape_date)
        for field in coll_entry['fields']:
            inv.log_dest.info("            Processing "+field)
            invc.set_field(db, _c_id['id'], field, coll_entry['fields'][field])
        for record in coll_entry['records']:
            inv.log_dest.info("            Processing "+record)
            rec_hash = ih.hash_record_schema(coll_entry['records'][record]['schema'])
            rec_entry = invc.get_record(db, _c_id['id'], rec_hash)
            if rec_entry['exist']:
                invc.update_record_count(db, rec_entry['id'], coll_entry['records'][record]['count'])
            else:
                invc.set_record(db, _c_id['id'], coll_entry['records'][record])

    except Exception as e:
        inv.log_dest.error("Failed to refresh collection "+str(e))

    orphaned_keys = []
    if not fresh:
        try:
	    #Trim any human table keys which are now redundant
            orphaned_keys = invc.trim_human_table(db, db_entry['id'], _c_id['id'])
        except Exception as e:
            inv.log_dest.error("Failed to refresh collection "+str(e))
    return orphaned_keys

def extract_specials(coll_entry):
    """ Split coll_entry into data and specials (notes, info etc) parts """
    notes = ''
    notes_entry = ''
    info = ''
    info_entry = ''
    for item in coll_entry:
        if item == inv.STR_NOTES:
            notes = item
            notes_entry = coll_entry[item]
        elif item == inv.STR_INFO:
            info = item
            info_entry = coll_entry[item]
    try:
        coll_entry.pop(notes)
        coll_entry.pop(info)
    except:
        pass
    return {inv.STR_NOTES:notes_entry, inv.STR_INFO: info_entry, 'data': coll_entry}

def read_file(filename):
    """Read entire file contents """
    with open(filename, 'r') as in_file:
        dat = in_file.read()
    return dat

def read_list(listfile):
    """Read file line-wise into list of lines """
    with open(listfile, 'r') as in_file:
        lines = in_file.read().splitlines()
    return lines

#End upload routines -----------------------------------------------------------------

#Table removal -----------------------------------------------------------------------
def delete_contents(db, tbl_name, check=True):
    """Delete contents of tbl_name """

    if not inv.validate_mongodb(db) and check:
        raise TypeError("db does not match Inventory structure")
        return
    #Grab the possible table names
    tbl_names = inv.get_inv_table_names()
    if tbl_name in tbl_names:
        try:
            db[tbl_name].remove()
        except Exception as e:
            inv.log_dest.error("Error deleting from "+ tbl_name+' '+ str(e)+", dropping")
            #Capped tables, e.g rollback, can only be dropped, so try that
	    try:
		db[tbl_name].drop()
            except Exception as e:
                inv.log_dest.error("Error dropping "+ tbl_name+' '+ str(e))

def delete_table(db, tbl_name, check=True):
    """Delete tbl_name (must be empty) """

    if not inv.validate_mongodb(db) and check:
        raise TypeError("db does not match Inventory structure")
        return
    #Grab the possible table names
    tbl_names = inv.get_inv_table_names()
    if tbl_name in tbl_names:
        try:
	    assert(db[tbl_name].find_one() is None) #Check content is gone
            db[tbl_name].drop()
        except Exception as e:
            inv.log_dest.error("Error dropping "+ tbl_name+' '+ str(e))
            #Capped tables, e.g rollback, can only be dropped, so try that

def unsafe_delete_all_tables(db):
    """Delete inventory tables by name without checking this really is the inventory db
    use if inv.validate_mongod fails and you know some table is missing and you are sure db is the inventory"""

    tbls = inv.get_inv_table_names()
    for tbl in tbls:
        try:
            delete_contents(db, tbl, check=False)
            delete_table(db, tbl, check=False)
        except Exception as e:
            inv.log_dest.error("Error deleting "+ tbl + ' ' +str(e))

def delete_all_tables(db):
    """ Delete all tables specified by inv Note that other names can be present, see inv.validate_mongod"""

    if not inv.validate_mongodb(db):
        raise TypeError("db does not match Inventory structure")
        return
    tbls = inv.get_inv_table_names()
    for tbl in tbls:
        try:
            delete_contents(db, tbl)
            delete_table(db, tbl)
        except Exception as e:
            inv.log_dest.error("Error deleting "+ tbl + ' ' +str(e))

def delete_collection_data(inv_db, coll_id, tbl='auto'):
    """Clean out the data for given collection id
      Removes all entries for coll_id in auto or human table
    """
    try:
        fields_tbl = inv.ALL_STRUC.get_fields(tbl)[inv.STR_NAME]
        fields_fields = inv.ALL_STRUC.get_fields(tbl)[inv.STR_CONTENT]
        rec_find = {fields_fields[1]:coll_id}
        inv_db[fields_tbl].remove(rec_find)
    except Exception as e:
        inv.log_dest.error("Error removing fields " + str(e))

def delete_by_collection(inv_db, db_name, coll_name):
    """Remove collection entry and all its fields"""

    if not inv.validate_mongodb(inv_db):
        raise TypeError("db does not match Inventory structure")
        return

    try:
        _db_id = invc.get_db_id(inv_db, db_name)
        _c_id = invc.get_coll_id(inv_db, _db_id['id'], coll_name)
    except Exception as e:
        inv.log_dest.error("Error getting collection " + str(e))
        return {'err':True, 'id':0, 'exist':False}

    #Remove fields entries matching _c_id
    delete_collection_data(inv_db, _c_id['id'], tbl='auto')
    delete_collection_data(inv_db, _c_id['id'], tbl='human')

    try:
        inv_db[inv.ALL_STRUC.coll_ids[inv.STR_NAME]].remove({'_id':_c_id['id']})
    except Exception as e:
        inv.log_dest.error("Error removing collection " + str(e))


#End table removal -----------------------------------------------------------------------

#Initial uploader routines ---------------------------------------------------------------

def fresh_upload(master_file_name, list_file_name):
    """Delete existing data and upload a fresh copy.
    CLOBBERS ALL EXISTING CONTENT
      Arguments :
      master_file_name -- path to structure file from report tool (e.g. lmfdb_structure.json)
      list_file_name -- path to file containing names of all json files to upload (one per collection)
    """
    got_client = inv.setup_internal_client(editor=True)
    if not got_client:
        inv.log_dest.error("Cannot connect to db")
        return
    db = inv.int_client[inv.get_inv_db_name()]

    #DELETE all existing inventory!!!
    delete_all_tables(db)

    upload_from_files(db, master_file_name, list_file_name, fresh=True)
    recreate_rollback_table(db, MAX_SZ)

def fresh_upload_coll(db_name, coll_name, master_file_name, json_file_name):
    """Delete existing data and upload a fresh copy for a single collection.
    CLOBBERS ALL EXISTING CONTENT FOR THIS COLLECTION
      Arguments :
      db_name -- name of database to refresh
      coll_name -- name of collection to refresh
      master_file_name -- path to structure file from report tool (entire or single collection)
      json_file_name -- path to additional json file for this collection
    """
    got_client = inv.setup_internal_client(editor=True)
    if not got_client:
        inv.log_dest.error("Cannot connect to db")
        return
    db = inv.int_client[inv.get_inv_db_name()]

    delete_by_collection(db, db_name, coll_name)
    upload_collection_from_files(db, db_name, coll_name, master_file_name, json_file_name, fresh=True)

def recreate_rollback_table(inv_db, sz):
    """Create anew the table for edit rollbacks

    Arguments :
    inv_db -- LMFDB db connection to inventory table
    sz -- Max size of the capped table
    If table exists, it is now deleted
    """
    try:
        table_name = inv.ALL_STRUC.rollback_human[inv.STR_NAME]
        coll = inv_db[table_name]
    except Exception as e:
        inv.log_dest.error("Error getting collection "+str(e))
        return {'err':True, 'id':0}
    fields = inv.ALL_STRUC.rollback_human[inv.STR_CONTENT]

    try:
        inv_db[table_name].drop()
    except:
        #TODO Do something useful here?
        pass

    inv_db.create_collection(table_name, capped=True, size=sz)

if __name__ == "__main__":

    got_client = inv.setup_internal_client(editor=True)
    if not got_client:
        exit()
    db = inv.int_client[inv.get_inv_db_name()]

    master_file_name = "./lmfdb/lmfdb_report_tool-master/intermediates/lmfdb_structure.json"
    list_file_name = "descr.txt"
    fresh_upload(master_file_name, list_file_name)

    tbls = inv.get_inv_table_names()
    for tbl in tbls:
        print(tbl)
        for item in db[tbl].find():
            try:
                print('   '+item['name'])
                print('       '+str(item['data']))
            except:
                pass
