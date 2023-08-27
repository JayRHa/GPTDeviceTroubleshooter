import streamlit as st
import os
from modules.utility import *
from msal_streamlit_authentication import msal_authentication

st.set_page_config(page_title="GPT Intune Device Troubleshooter", page_icon ="chart_with_upwards_trend", layout = 'wide')

#################################################################################
################################# Vars ##########################################
#################################################################################
category_list = ['GetDeviceList', 'GetDeviceStatus', 'GetSingleDevice', 'IntuneHowTo', 'ConfigProfiles', 'AppList', 'CompliancePolicies', 'DeviceGroupMembership', 'GraphCall']

if "category" not in st.session_state:
    st.session_state["category"] = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "login_token" not in st.session_state:
    st.session_state.login_token = {}
if "graph_auth_header" not in st.session_state:
    st.session_state.graph_auth_header = {}
if "devicename" not in st.session_state:
    st.session_state.devicename = ""
if "username" not in st.session_state:
    st.session_state.username = ""
if "question" not in st.session_state:
    st.session_state.question = ""
if "user_want_skip" not in st.session_state:
    st.session_state.user_want_skip = False
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

st.session_state.azure_openai_key = os.environ["AZURE_OPENAI_KEY"]
st.session_state.azure_openai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
st.session_state.azure_openai_deployment = os.environ["AZURE_OPENAI_CHATGPT_DEPLOYMENT"]

login_token = None

#################################################################################
################################# Functions #####################################
#################################################################################
def get_graph_access_token(token):
    return {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {token}"
    }

def ask_for_device_name(device_name):
    if device_name is None or device_name == 'None' or device_name == '':
        question = "Can you enter the device name of the device which you want to analyse?"
        with st.chat_message("assistant"):
            st.markdown(question)
        st.session_state.messages.append({"role": "assistant", "content": question})
        return False
    else:
        return True
    

def write_assistant_answer(text, logging=True):
    with st.chat_message("assistant"):
        st.markdown(text)
    if logging:
        st.session_state.messages.append({"role": "assistant", "content": text})


clinet_id = os.environ["APPLICATION_ID"]
redirect_uri = os.environ["REDIRECT_URI"]
tenant_id = os.environ["AZURE_TENANT_ID"]
#################################################################################
################################# Sidebar #######################################
#################################################################################
with st.sidebar:
    # Login
    login_token = msal_authentication(
    auth={
        "clientId": f"{clinet_id}",
        "authority": f"https://login.microsoftonline.com/{tenant_id}",
        "redirectUri": f"{redirect_uri}",
        "postLogoutRedirectUri": "/"
    },
    cache={
        "cacheLocation": "sessionStorage",
        "storeAuthStateInCookie": False
    },
    logout_request={},
    login_button_text="Login",
    logout_button_text="Logout",
    html_id="html_id_for_button",
    key=1
    )

    if login_token is not None:
        st.session_state.logged_in = True
        st.session_state.login_token = login_token
        st.sidebar.write("Welcome:", st.session_state.login_token['account']['name'])
        
        st.session_state.graph_auth_header = get_graph_access_token(st.session_state.login_token['accessToken'])

    #st.sidebar.write("Category: ", st.session_state["category"])

    st.sidebar.markdown("---")
    clear_button = st.button("Clear Conversation", key="clear")
 

util = utility(
    azure_openai_key=st.session_state.azure_openai_key
    ,azure_openai_endpoint = st.session_state.azure_openai_endpoint
    ,azure_openai_deployment=st.session_state.azure_openai_deployment
    ,graph_auth_header=st.session_state.graph_auth_header
)

if clear_button:
    st.session_state["category"] = ""
    st.session_state.messages = []
    st.session_state.devicename = ""
    st.session_state.username = ""
    st.session_state.question = ""
    st.session_state.user_want_skip = False
    reset = False


download_conversation_button = st.sidebar.download_button(
    "Download Conversation",
    data=json.dumps(st.session_state["messages"]),
    file_name=f"conversation.json",
    mime="text/json",
)


#################################################################################
################################# Main ##########################################
#################################################################################
with st.chat_message("assistant"):
    st.markdown("Welcome I am your GPT Intune Troubleshooting Assistant. How can I help you?")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


reset = False
if prompt := st.chat_input("Welcome I am your GPT Intune Troubleshooting Assistant. How can I help you?"):
    if not st.session_state.logged_in:
        with st.chat_message("assistant"):
            st.markdown("You are not logged in. Please login first.")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if st.session_state["category"] is None or st.session_state["category"] == 'None' or st.session_state["category"] == '':
            response = util.get_category(category_list, prompt)
            st.session_state["category"] = response["category"]  
            st.session_state["devicename"] = response["devicename"] #It non than blabla
            st.session_state["username"] = response["username"]
            st.session_state["question"] = response["question"]
        else:
            response = util.get_info_from_prompt(prompt, st.session_state["question"])
            st.session_state["user_want_skip"] = response["user_want_skip"]
            st.session_state["devicename"] = response["devicename"]
            st.session_state["username"] = response["username"]

        if st.session_state["user_want_skip"]:
            reset = True
        else:
            if st.session_state["category"] is None or st.session_state["category"] == 'None' or st.session_state["category"] == '':
                write_assistant_answer("This question does not fit any of the predefined categories, but I'll try to answer the question.", logging=False)
                answer = util.invoke_gpt_call(user=prompt, history=st.session_state.messages)
                write_assistant_answer(answer)
                st.session_state["category"] = None
            elif st.session_state["category"] == 'GetDeviceList':
                answer = util.get_device_list(question=prompt, history=st.session_state.messages)
                write_assistant_answer(answer)
                st.session_state["category"] = None
            elif st.session_state["category"] == 'GetDeviceStatus':
                if ask_for_device_name(st.session_state["devicename"]):
                    answer = util.get_device_status(device_name=st.session_state["devicename"], question=prompt, history=st.session_state.messages)
                    write_assistant_answer(answer)
                    st.session_state["category"] = None
            elif st.session_state["category"] == 'GetSingleDevice':
                if ask_for_device_name(st.session_state["devicename"]):
                    answer = util.get_device_info(device_name=st.session_state["devicename"], question=prompt, history=st.session_state.messages)
                    write_assistant_answer(answer)
                    st.session_state["category"] = None
            elif st.session_state["category"] == 'ConfigProfiles':
                answer = util.get_config_profiles(question=prompt, history=st.session_state.messages)
                write_assistant_answer(answer)
                st.session_state["category"] = None
            elif st.session_state["category"] == 'AppList':
                answer = util.get_apps(question=prompt, history=st.session_state.messages)
                write_assistant_answer(answer)
                st.session_state["category"] = None
            elif st.session_state["category"] == 'CompliancePolicies':
                answer = util.get_compliance_policies(question=prompt, history=st.session_state.messages)
                write_assistant_answer(answer)
                st.session_state["category"] = None
            elif st.session_state["category"] == 'DeviceGroupMembership':
                if ask_for_device_name(st.session_state["devicename"]):
                    answer = util.get_device_group_membership(st.session_state["devicename"], question=prompt, history=None)
                    write_assistant_answer(answer)
                    st.session_state["category"] = None
            elif st.session_state["category"] == 'IntuneHowTo':
                pass
                st.session_state["category"] = None
            elif st.session_state["category"] == 'GraphCall':
                graph_call = util.get_graph_url(question=prompt, history=st.session_state.messages)
                print(graph_call)
                if(graph_call['graph_call'] is not None):
                    answer = util.run_graph_call(graph_call=graph_call['graph_call'], question=prompt, history=st.session_state.messages)
                    answer
                    write_assistant_answer(answer)
                    st.session_state["category"] = None
                else:
                    write_assistant_answer("No graph url found. Please try again")
            else:
                write_assistant_answer("Something went wrong. The category was not found. Please try again")
    if reset is True:
        st.session_state["category"] = None
        st.session_state["devicename"] = None
        st.session_state["username"] = None
        st.session_state["question"] = None
        st.session_state["user_want_skip"] = None
        reset = False