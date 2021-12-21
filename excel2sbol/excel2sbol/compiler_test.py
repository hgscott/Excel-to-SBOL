import pandas as pd
import os
import excel2sbol.helper_functions as hf
import excel2sbol.lookup_compiler as lk
import excel2sbol.comp_column_functions as cf
import sbol2
import math
import re

homespace_url = "http://examples.org/"
# homespace_url = ''
cwd = os.getcwd()
file_path_in = os.path.join(cwd, 'excel2sbol', 'tests', 'test_files', 'pichia_comb_dev_compiler.xlsx')
file_path_out = os.path.join(cwd, 'out.xml')

init_info = pd.read_excel(file_path_in, sheet_name="Init",
                          skiprows=9, index_col=0,
                          engine='openpyxl').to_dict('index')


# For key in dict read in sheet, if sheet convert = true, add to convert list
compiled_sheets = {}
to_convert = []
for sheet_name, val in init_info.items():
    convert = val['Convert']

    if convert:
        to_convert.append(sheet_name)

    # read in collections, description, library
    sheet_dict = {}

    if val['Has Collections']:
        x = val['Collect Cols']
        x = x.split(',')
        x = [int(i) for i in x]

        sheet_dict['collection_info'] = pd.read_excel(file_path_in, sheet_name=sheet_name,
                                    header=None, nrows=val['# of Collect Rows'],
                                    usecols=x,
                                    index_col=0, engine='openpyxl').to_dict('index')
    else:
        sheet_dict['collection_info'] = {}

    if val['Has Descripts']:
        x = val['Descript Cols']
        if isinstance(x, float):
            x = int(x)
            x = [x]
        elif isinstance(x, str):
            x = x.split(',')
            x = [int(i) for i in x]

        sheet_dict['description'] = pd.read_excel(file_path_in, sheet_name=sheet_name,
                                     header=None,
                                     skiprows=int(val['Descript Start Row']), nrows=1,
                                     usecols=x, engine='openpyxl').iloc[0, 0]
    else:
        sheet_dict['description'] = ""

    sheet_dict['library'] = pd.read_excel(file_path_in, sheet_name=sheet_name,
                                          header=0,
                                          skiprows=val['Lib Start Row'],
                                          engine='openpyxl').fillna("").to_dict('list')

    # need dicitonary with as keys every column name and as values a list of values (note ordered list and need place holder empty values)
    compiled_sheets[sheet_name] = sheet_dict

# read in column_dict sheet
col_read_df = pd.read_excel(file_path_in,
                                 sheet_name="column_definitions", header=0,
                                 engine='openpyxl')

# col_read_df = col_read_df.to_dict('index')


################################################################
"""Making a list of all objects in the document"""

# create uris for every item in to convert sheets (note might want generic top level if object type is not an sbol object type)
dict_of_objs = {}
doc = sbol2.Document()
sbol2.setHomespace('http://examples.org/')
sbol2.setHomespace('')
# sbol2.Config.setOption(sbol2.ConfigOptions.SBOL_COMPLIANT_URIS, False)
sbol2.Config.setOption(sbol2.ConfigOptions.SBOL_TYPED_URIS, False)


def non_implemented_class(types, uri):
    tp = sbol2.TopLevel(type_uri=types, uri=uri, version='1')
    return tp


sht_convert_dict = {}
for sht in to_convert:
    sht_df = col_read_df.loc[col_read_df['Sheet Name'] == sht]

    try:
        dis_name_col = sht_df.loc[col_read_df['SBOL Term'] == 'sbol_displayId']['Column Name'].values[0]
    except IndexError as e:
        raise KeyError(f'The sheet "{sht}" has no column with sbol_displayID as type. Thus the following error was raised: {e}')

    try:
        obj_type_col = sht_df.loc[col_read_df['SBOL Term'] == 'sbol_objectType']['Column Name'].values[0]
    except IndexError as e:
        raise KeyError(f'The sheet "{sht}" has no column with sbol_objectType as type. Thus the following error was raised: {e}')

    sht_convert_dict[sht] = dis_name_col
    ids = compiled_sheets[sht]['library'][dis_name_col]
    types = compiled_sheets[sht]['library'][obj_type_col]

    for ind, id in enumerate(ids):
        sanitised_id = hf.check_name(id)
        uri = f'{homespace_url}{sanitised_id}'
        dict_of_objs[id] = uri

        if hasattr(sbol2, types[ind]):
            varfunc = getattr(sbol2, types[ind])
            obj = varfunc(uri)
            obj.displayId = sanitised_id

        else:
            obj = non_implemented_class(types[ind], uri)

        dict_of_objs[id] = {'uri': uri, 'object': obj}

# check all uris have been made for the id lookup columns, make any not yet called and call warning
# can move this to where the column is processed and if it causes difficulties call an error there.
# all id lookup and parent lookup columns
# id_lookup_rows = col_read_df.loc[col_read_df['Object_ID Lookup'] == True]

for obj_name in dict_of_objs:
    obj = dict_of_objs[obj_name]['object']
    doc.add(obj)

###########################################################################
# parse columns of all to convert sheets

for sht in to_convert:
    print(sht)
    sht_lib = compiled_sheets[sht]['library']
    num_rows = len(sht_lib[list(sht_lib.keys())[0]])  # pulls first column and checks the number of elements in it

    for row_num in range(0, num_rows):
        disp_id = sht_lib[sht_convert_dict[sht]][row_num]
        obj = dict_of_objs[disp_id]['object']
        obj_uri = dict_of_objs[disp_id]['uri']

        for col in sht_lib.keys():
            cell_val = sht_lib[col][row_num]

            if cell_val != '':
                # checks that the cell isn't blank
                col_convert_df = col_read_df.loc[(col_read_df['Sheet Name'] == sht) & (col_read_df['Column Name'] == col)]

                # split method
                split_on = col_convert_df['Split On'].values[0]
                split_on = split_on.split('"')
                split_on = [x for x in split_on if x != '']
                split_on = '[' + "".join(split_on) + ']'
                if len(split_on) > 2:  # used as string will always be '[]' at least
                    cell_val = re.split(split_on, cell_val)
                if isinstance(cell_val, list):
                    cell_val = [x.strip() for x in cell_val]

                # cell value or list of cell values based on lookups
                if isinstance(cell_val, list):
                    for ind, val in enumerate(cell_val):
                        cell_val[ind] = lk.up(col_convert_df, val, compiled_sheets, dict_of_objs)
                else:
                    cell_val = lk.up(col_convert_df, cell_val, compiled_sheets, dict_of_objs)

                # if converted to empty cell or empty string then skip the rest
                is_nan = False
                if isinstance(cell_val, float):
                    is_nan = math.isnan(cell_val)
                if cell_val == "" or is_nan:
                    continue

                # Ensures that the cell value after possible conversion
                # matches one of the patterns specified
                pattern = col_convert_df['Pattern'].values[0]
                if isinstance(pattern, str) and len(pattern) > 2:
                    pattern = pattern = pattern.split('"')
                    pattern = [x for x in pattern if x != '' and x != ' ']
                    if isinstance(cell_val, list):
                        for val in cell_val:
                            pat_truth = [re.match(pat, val) for pat in pattern]
                            pat_truth = [True for pat in pat_truth if pat is not None]
                            if len(pat_truth) < 1:
                                raise ValueError(f'The cell value provided did not meet (any of) the pattern criteria, cell value: {val}, pattern:{pattern}')
                    else:
                        pat_truth = [re.match(pat, cell_val) for pat in pattern]
                        pat_truth = [True for pat in pat_truth if pat is not None]
                        if len(pat_truth) < 1:
                            raise ValueError(f'The cell value provided did not meet (any of) the pattern criteria, cell value: {cell_val}, pattern:{pattern}')

                # carry out method of column processing based on
                # the sbol_term of the column
                parental_lookup = col_convert_df['Parent Lookup'].values[0]
                col_meth = cf.sbol_methods(col_convert_df['Namespace URL'].values[0],
                                           obj, obj_uri, dict_of_objs, doc,
                                           cell_val,
                                           col_convert_df['Type'].values[0],
                                           parental_lookup,
                                           homespace_url)
                col_meth.switch(col_convert_df['SBOL Term'].values[0])



doc.write(file_path_out)
# output sbol
