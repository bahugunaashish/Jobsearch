import csv
import io
import streamlit as st
from iit_nit_vacancies import SITES, crawl

st.set_page_config(page_title='Faculty Vacancy Monitor', page_icon='🎓', layout='wide')
st.title('🎓 IIT & NIT Faculty Vacancy Monitor')
st.caption('Search institute websites directly for Assistant Professor recruitment notices.')
st.info('Results are potential matches. Check the official notice for the post, eligibility and deadline. Some sites may be missed or inaccessible.')
with st.sidebar:
    st.header('Search settings')
    groups=st.multiselect('Institutes', list(SITES), default=list(SITES))
    limit=st.slider('Maximum pages per institute', 5, 50, 20)
    st.caption('A full search may take several minutes. The app searches when you press the button; daily email requires separate scheduling.')
if st.button('Search institute websites', type='primary', disabled=not groups):
    results={}; issues=[]; coverage=[]
    progress=st.progress(0, text='Starting search')
    for i, name in enumerate(groups):
        progress.progress(i/len(groups), text=f'Checking {name} ({i+1}/{len(groups)})')
        found, errors, count=crawl(name, SITES[name], limit, 0.5)
        for hit in found: results[(hit['institute'],hit['url'])]=hit
        issues.extend(errors); coverage.append({'Institute':name,'Pages attempted':count,'Issues':len(errors)})
    progress.progress(1.0, text='Search complete')
    st.session_state['results']=list(results.values())
    st.session_state['issues']=issues
    st.session_state['coverage']=coverage
if 'results' in st.session_state:
    results=st.session_state['results']
    st.subheader(f'{len(results)} potential matches')
    query=st.text_input('Filter results', placeholder='Institute, title or keyword').lower().strip()
    selected=[h for h in results if not query or query in ' '.join(str(x) for x in h.values()).lower()]
    if not selected: st.write('No matching results found.')
    for h in selected:
        with st.container(border=True):
            st.markdown(f"**{h['institute']}**")
            st.write(h['title'])
            st.write('Possible deadline:', h['deadline'])
            st.link_button('Open official notice', h['url'])
    buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=['institute','title','url','deadline','evidence']); w.writeheader(); w.writerows(selected)
    st.download_button('Download results as CSV',buf.getvalue(),'faculty_vacancies.csv','text/csv')
    with st.expander('Search coverage and issues'):
        st.dataframe(st.session_state['coverage'],hide_index=True)
        for error in st.session_state['issues']: st.write(error)
