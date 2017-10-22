import re
import ast
from flask_sqlalchemy import SQLAlchemy
#from mealplanner import models_food
from flask import Flask, redirect, render_template, json, request, jsonify, url_for, session
from mealplanner.forms import SearchForm
import sqlalchemy
from sqlalchemy.sql import text
from sqlalchemy import Table, Column, Integer, String, ForeignKey
import pandas as pd
import sys
from fuzzywuzzy import fuzz


app = Flask(__name__)

app.config.from_object('config')

db = SQLAlchemy(app)
db.init_app(app)

# The return value of create_engine() is our connection object
engine = sqlalchemy.create_engine(app.config['SQLALCHEMY_DATABASE_URI'], client_encoding='utf8')

def getIDforIngredient(name):
    conn = engine.connect()
    sql = "SELECT i.* FROM ingredient i, UNNEST(alt_names) names WHERE (lower(i_name) = \'%s\') OR (lower(names) = \'%s\')" % (name, name)
    print(sql)
    result = conn.execute(sql).fetchone()
    return result['iid'] if result['iid'] is not None else None

'''
if not con.dialect.has_table(con, 'recipe'):  # If table don't exist, Create.
    recipe = Table('recipe', meta,
			   Column('id', Integer, primary_key=True),
			   Column('name', String), 
    		   Column('description', String), 
			   Column('steps', String)
			   )

    ingredients = Table('ingredients', meta,
	    				Column('recipeid', Integer, ForeignKey('recipe.id')), 
		    			Column('ingredient', String)
			    		)

    #create above tables
    meta.create_all(con)
'''
toInsert = [
    {'id': 1, 'name': 'chocolate cake', 'description': 'this is chocolate cake', 'steps': '1. mix ingredients 2.bake'}
]
# con.execute(meta.tables['recipe'].insert(), toInsert)

toInsert = [
    {'recipeid': 1, 'ingredient': 'flour'},
    {'recipeid': 1, 'ingredient': 'cocoa'},
    {'recipeid': 1, 'ingredient': '3 eggs'},
    {'recipeid': 1, 'ingredient': 'butter'}
]


# con.execute(meta.tables['ingredients'].insert(), toInsert)



# main page
@app.route('/', methods=['GET', 'POST'])
@app.route('/<tags>', methods=['GET', 'POST'])
def main(tags=None): 
    tagarray=[]
    gettags = tags
    if tags != None:
        tagarray=gettags.split(",")
        tagarray= [re.search("'.*'", elem, flags=0).group() for elem in tagarray]
        tagarray= [re.sub("'", '', elem) for elem in tagarray]
    if request.method == 'POST':
        print('if', file=sys.stderr)
        _query = request.form['query']
        if request.form['submit'] == 'Search':
            tagarray.append(_query)
            try:
                form = SearchForm()
                return redirect(url_for('search_recipe', query=tagarray))
            except Exception as e:
                form = SearchForm()
                return render_template('index.html',
                                       title='Home',
                                       form=form)

        if request.form['submit'] == 'Add':
            tagarray.append(_query)
            for tag in tagarray:
                print(tag)
            try:
                form = SearchForm()
                return redirect(url_for('main', tags=tagarray))

            except Exception as e:
                form = SearchForm()
                return render_template('index.html',
                                       title='Home',
                                       form=form)

    else:
        print('else', file=sys.stderr)
        form = SearchForm()
        # if form.validate_on_submit():
        return render_template('index.html',
                               title='Search',
                               form=form, tags=tagarray)
    return render_template('index.html')


# result page
@app.route('/result/<query>', methods=['GET', 'POST'])
def result(query):
    q = text("Select * from ingredient where i_name like :i")
    result = engine.execute(q, i=query).fetchall()
    print(result)
    resultset = [dict(row) for row in result]
    df = pd.DataFrame(data=result, columns=['iid', 'i_name', 'i_description', 'ic_id'])
    print(df)
    print(resultset)
    form = SearchForm()
    return render_template('result.html',
                           title='Results',
                           form=form, data=df.to_html())


"""
    :param      query    str type that can be any case
    :return     df       the top 5 result in json format
"""


@app.route('/autocomplete',methods=['GET'])
def autocomplete():
    # remove all the non-alphabet chars
    query = request.args.get('q')
    query = str.lower(str(query))
    re.sub(r'[^a-zA-Z]', '', query)
    ingredients = dict()
    unique_list = []
    results = []
    conn = engine.connect()
    sql = 'SELECT i.* FROM ingredient i, UNNEST(alt_names) names WHERE (lower(i_name) ~ \'(^|\\s)%s\') OR ' \
          '(lower(names) ~ \'(^|\\s)%s\') ORDER BY iid ASC LIMIT 100' % (query, query)
    rs = conn.execute(sqlalchemy.text(sql))
    results = []
    unique_list = []
    for row in rs:
        if row['i_name'] in unique_list:
            continue
        unique_list.append(row['i_name'])
        all_names = [row['i_name']] + row['alt_names']
        all_names.sort(key = lambda name: fuzz.ratio(query, name), reverse=True)
        results.append((all_names[0], fuzz.ratio(query, all_names[0])))

    results.sort(key = lambda res: res[1], reverse = True)
    results = [r[0] for r in results]

    if(len(results) > 5):
        max_res = 4
    else:
        max_res = len(results)-1

    results = results[0:max_res]
    
    print(jsonify(matching_result=results))

    return jsonify(matching_results=results)


def create_extension():
    conn = engine.connect()

    sql = 'CREATE EXTENSION IF NOT EXISTS intarray'
    conn.execute(sql)


def init_array(alist):
    parray = 'ARRAY['
    i = 1
    for x in alist:
        if i == len(alist):
            parray += str(x) + ']'
        else:
            parray += str(x) + ','
        i += 1
    print(parray)
    return str(parray)


"""
    :param      query    of str type (recipe title) or int type (ingredient id)
    :return        
"""
@app.route('/search_recipe/<query>', methods=['GET'])
def search_recipe(query):
    qlist = []
    query = ast.literal_eval(query)
    print(query)
    for q in query:
        if q != '':
            iid = getIDforIngredient(str(q).lower())
            if iid is not None:
                qlist.append(iid)

    create_extension()

    conn = engine.connect()

    recipes = []

    sql = "SELECT r_name, r_img, r_description, r_url, i_ids, (100.0*array_length(i_ids & %s,1))/array_length(i_ids,1) AS ct FROM recipe ORDER  BY 6 DESC NULLS LAST LIMIT 100 OFFSET 0" % init_array(qlist)  # add LIMIT to restrict to specific # of output
    rs = conn.execute(sqlalchemy.text(sql))
    for row in rs:
        res = []
        res.append(row['r_img'])
        res.append(row['r_name'])
        res.append(row['r_description'])
        res.append(row['r_url'])
        print(round(len(qlist)/len(row['i_ids']),2))
        res.append(round(len(qlist)/len(row['i_ids']),2))
        recipes.extend([res])
        print(recipes)


    #print(sql)
    return render_template('result.html', recipes = recipes, mod = 4)

'''
@app.route('/autocomplete',methods=['GET'])
def autocomplete():

    search = request.args.get('q')
    conn = engine.connect()
    #cursor = conn.cursor()
    sql="select i_name from ingredient where i_name like '%"+search+"%' limit 10"
    rs=conn.execute(sqlalchemy.text(sql))
    symbols = rs.fetchall()
    results = [mv[0] for mv in symbols]
    print(results)
    
    #cursor.close()
    conn.close()

    print(jsonify(matching_results=results))
    return jsonify(matching_results=results)
'''

@app.route('/signUpUser', methods = ['GET','POST'])
def signUpUser():
    conn = engine.connect()
    sql = "SELECT * FROM users WHERE users.u_email='%s'" % (request.form['inputEmail'])
    result = conn.execute(sql).fetchall()
    if len(result) < 1 and request.form['inputPassword'] == request.form['inputPasswordRpt']:
        sql = "INSERT INTO users (u_name,u_email,u_password) VALUES ('%s','%s','%s');" % ('',request.form['inputEmail'],request.form['inputPassword'])
        conn.execute(sql)
    return redirect(url_for('main'))

@app.route('/signInUser', methods = ['GET','POST'])
def signInUser():
    conn = engine.connect()
    sql = "SELECT * FROM users WHERE users.u_email='%s' AND users.u_password='%s';" % (request.form['inputEmail'],request.form['inputPassword'])
    result = conn.execute(sql).fetchall()
    if len(result) == 1 and not 'userEmail' in session:
        session['userEmail'] = request.form['inputEmail']

    return redirect(url_for('main'))

@app.route('/signOut', methods = ['GET','POST'])
def signOut():
    if 'userEmail' in session:
        session.pop('userEmail')
    return redirect(url_for('main'))

app.secret_key = 'hooray'
