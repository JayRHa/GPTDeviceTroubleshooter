import requests
import json
import re
import streamlit as st

BASE_URL = "https://graph.microsoft.com/beta/"

##################
#invoke_gpt_call
##################

class utility:
    def __init__(self, azure_openai_key, azure_openai_endpoint, azure_openai_deployment, graph_auth_header):
        self.azure_openai_key = azure_openai_key
        self.azure_openai_endpoint = azure_openai_endpoint
        self.azure_openai_deployment = azure_openai_deployment
        self.graph_auth_header = graph_auth_header
    
    def invoke_gpt_call(self,user,system=None,history=None):
        headers = {
            "Content-Type": "application/json",
            "api-key": self.azure_openai_key
        }

        messages = []

        if system is not None:
            messages.append({
                "role": "system",
                "content": system
            })

        if history is not None:
             messages = messages + history

        messages.append({
            "role": "user",
            "content": user
        })

        body = {
            "messages": messages,
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.azure_openai_endpoint}/openai/deployments/{self.azure_openai_deployment}/chat/completions?api-version=2023-05-15", headers=headers, data=json.dumps(body))
            response.raise_for_status()
            response_data = response.json()
            return response_data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error while executing a call to {self.azure_openai_endpoint}: {e}")
            return None


#################################################################################################
############################################# Graph #############################################
#################################################################################################
    def get_graph_call_custom(self, endpoint, value=True):
        uri = BASE_URL + endpoint
        try:
            response = requests.get(uri, headers=self.graph_auth_header)
        except Exception as e:
            print(f"Error while executing a call to {uri}: {e}")
            raise(f"Error while executing a call to {uri}: {e}")
        
        response.raise_for_status()

        if value:
            return response.json().get('value', {})
        else:
            return response.json()
        
    # ToDo: Add error handling

    def get_apps_graph(self):
        return self.get_graph_call_custom('deviceAppManagement/mobileApps?$filter=(microsoft.graph.managedApp/appAvailability%20eq%20null%20or%20microsoft.graph.managedApp/appAvailability%20eq%20%27lineOfBusiness%27%20or%20isAssigned%20eq%20true)&$orderby=displayName&$select=id,createdDateTime,developer,displayName,isFeatured,lastModifiedDateTime,publisher,publishingState,categories')

    def get_config_profiles_graph(self):
        return self.get_graph_call_custom("deviceManagement/deviceConfigurations?$top=1000&$select=id,displayName,lastModifiedDateTime,roleScopeTagIds,createdDateTime&$orderBy=displayName%20asc")
    
    def get_compliance_policies_graph(self):
        return self.get_graph_call_custom("deviceManagement/compliancePolicies?$select=id,name,description,platforms,technologies,lastModifiedDateTime,settingCount,roleScopeTagIds,scheduledActionsForRule&$top=100")        

    def get_device_group_membership_graph(self):
        pass

    def get_intune_single_device_info(self, device_name):
        return self.get_graph_call_custom(f"deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'")

    def get_intune_all_devices_info(self):
        attributes = "userId,id,deviceName,lastSyncDateTime,enrolledDateTime,operatingSystem,osVersion,operatingSystem,complianceState,model,manufacturer,managementAgent,userPrincipalName"
        return self.get_graph_call_custom(f"deviceManagement/managedDevices?$select={attributes}")

    def get_aad_device_id(self, device_name):
        print(f"devices?$filter=displayName eq '{device_name}'&$select=id")
        return self.get_graph_call_custom(f"devices?$filter=displayName eq '{device_name}'&$select=id")[0]['id']

    def get_intune_device_id(self, device_name):
        return self.get_graph_call_custom(f"deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'&$select=id")[0]['id']

    def get_intune_user_id(self, device_name):
        return self.get_graph_call_custom(f"deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'&$select=userId")[0]['userId']

    def get_group_memberships_graph(self, device_name):
        aad_device_id = self.get_aad_device_id(device_name)
        url = f'devices/{aad_device_id}/transitiveMemberOf/$/microsoft.graph.group?$select=id,displayName,mailEnabled,securityEnabled,groupTypes,onPremisesSyncEnabled,mail,isAssignableToRole&$count=true'
        return self.get_graph_call_custom(url)
        
    def get_device_status_graph(self, device_name):
        device_id = self.get_intune_device_id(device_name)
        if not device_id:
            return False

        platform_types = ['android','androidforwork','androidworkprofile','ios','macos','WindowsPhone81','Windows81AndLater','Windows10AndLater','all']
        platform_filter = " or ".join([f"(platformType eq '{ptype}')" for ptype in platform_types])
        # Get configuration profiles
        endpoint_config_profiles = (f"deviceManagement/managedDevices/{device_id}/"
                                    f"deviceConfigurationStates?$select=displayName,state&$filter=({platform_filter})")
        config_profiles = self.get_graph_call_custom(endpoint_config_profiles)

        # Get compliance policies
        endpoint_compliance_policies = (f"deviceManagement/managedDevices/{device_id}/"
                                        f"deviceCompliancePolicyStates?$select=displayName,state&$filter=({platform_filter})")
        compliance_policies = self.get_graph_call_custom(endpoint_compliance_policies)
        # Get user id
        user_id = self.get_intune_user_id(device_name)
        endpoint_apps = f"users('{user_id}')/mobileAppIntentAndStates('{device_id}')"
        apps = self.get_graph_call_custom(endpoint_apps, value=False).get('mobileAppList', [])

        # Get device details
        endpoint_device = f"deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        device = self.get_graph_call_custom(endpoint_device)

        # Compile the results into a multi-line string
        state = f"""
        ## Config Profiles
        {config_profiles}

        ## Compliance Policies
        {compliance_policies}

        ## Apps
        {apps}

        ## Device Info
        {device}
        """
        return state

#################################################################################################
########################################### Prompts #############################################
#################################################################################################
    def get_category(self, category_list, question):
        system_message = (f"Can you categorize the given message into one of these categories {category_list}?"
                        " If the message clearly fits into a category, answer with the category name only."
                        " If not, write 'None' as the category."
                        " Additionally, please attempt to extract the devicename and username from the question."
                        " This is only necessary if these details are explicitly mentioned within the text."
                        " If not, leave the fields blank."
                        " Here's the expected response structure:"
                        " # Answer"
                        " Category:"
                        " Devicename:"
                        " Username:")
        response = self.invoke_gpt_call(system=system_message, user=question)
        print(response)
        # Parse the response string with regex
        category_match = re.search(r'Category:\s*(.*?)\s*(?=Devicename|$)', response, re.I | re.S)
        category = category_match.group(1).strip() if category_match else None

        devicename_match = re.search(r'Devicename:\s*(.*?)\s*(?=Username|$)', response, re.I | re.S)
        devicename = devicename_match.group(1).strip() if devicename_match else None

        username_match = re.search(r'Username:\s*(.*?)\s*$', response, re.I | re.S)
        username = username_match.group(1).strip() if username_match else None

        return {
            "category": category,
            "devicename": devicename,
            "username": username,
            "question": question
        }
    
    def get_info_from_prompt(self, prompt, question, history=None):
        system_message = f"""
        Please attempt to extract the 'devicename' and 'username' from the question. If either of these details is not explicitly defined within the question, leave the corresponding field empty. 
        If you want to skip this step, you can include the phrase 'UserWantSkip' in your input.

        The question is: {question}
        
        Always respond following the structure:
        
            # Answer
            Devicename: 
            Username: 
            UserWantSkip: 
        """
        
        response = self.invoke_gpt_call(user=prompt, system=system_message, history=history)

        # Extracting values using regular expressions
        devicename_match = re.search(r'Devicename:\s*(.*?)(?=Username:|UserWantSkip:|$)', response, re.DOTALL | re.IGNORECASE)
        username_match = re.search(r'Username:\s*(.*?)(?=UserWantSkip:|$)', response, re.DOTALL | re.IGNORECASE)
        user_want_skip_match = re.search(r'UserWantSkip:\s*(.*?)\s*$', response, re.DOTALL | re.IGNORECASE)

        devicename = devicename_match.group(1).strip() if devicename_match else None
        username = username_match.group(1).strip() if username_match else None
        user_want_skip = True if user_want_skip_match and user_want_skip_match.group(1).strip() else False

        return {
            "devicename": devicename,
            "username": username,
            "question": question,
            "user_want_skip": user_want_skip
        }

    def get_device_list(self, question, history=None):
        # Assuming there's a Python version of Get-IntuneAllDevicesInfo
        response = self.get_intune_all_devices_info()
        device_list = json.dumps(response)
        system_message = f""" Can you answer the question of the user form this list of devices. If there is not clear question then summarize the device info.:

        #Device List
        {device_list}
        """

        return self.invoke_gpt_call(system=system_message, user=question, history=history)


    def get_device_info(self, device_name, question, history=None):
        device_details = self.get_intune_single_device_info(device_name)
        if not device_details:
            return False

        device_details_json = json.dumps(device_details, indent=4)
        system_message = f"""
        Can you answer the question of the user form the device info attached here. If there is not a clear question then summarize the device info into a device state. If you see some issues also mention this. Can you output this result in a structured list and only show the issues of the device? If there are no issues, then mark it as healthy:

        #Device Info
        {device_details_json}
        """
        return self.invoke_gpt_call(question, system_message, history=history)
    
    def get_device_status(self, device_name, question, history=None):
        device_state = self.get_device_status_graph(device_name)
        if not device_state:
            return False
        system_message = f"""
        Can you answer the question of the user from the device status info attached here. If there is not clear question then summarize the status. If you see issues mention this.:

        #Device Status
        {device_state}
        """
        return self.invoke_gpt_call(question, system_message, history=history)      

    def get_apps(self, question, history=None):
        apps = self.get_apps_graph()
        system_message = f"""
        If the user is asking for a list of apps, provide them with the information of each app from the list below. If the answer is not clear from the list, summarize the apps available in the tenant.

        #App List
        {apps}        
        """
        return self.invoke_gpt_call(question, system_message, history=history)
    
    def get_config_profiles(self, question, history=None):
        config_profiles = self.get_config_profiles_graph()
        system_message = f"""
        Can you answer the question of the user form the list of config profiles attached here. If there is not clear question then summarize the config profile list.:

        #Config Profiles
        {config_profiles}
        """
        return self.invoke_gpt_call(question, system_message, history=history)
    
    def get_compliance_policies(self, question, history=None):
        compliance_policies = self.get_compliance_policies_graph()
        system_message = f"""
        Can you answer the question of the user form the list of compliance policies attached here. If there is not clear question then summarize the compliance policy list.:

        #Compliance Policies
        {compliance_policies}
        """
        return self.invoke_gpt_call(question, system_message, history=history)
    
    def get_device_group_membership(self, device_name, question, history=None):
        group_memberships = self.get_group_memberships_graph(device_name)
        system_message = f"""
        Can you answer the question of the user form the list of group memberships attached here. If there is not clear question then summarize the groups.:

        #Group membership list for {device_name}
        {group_memberships}
        """
        return self.invoke_gpt_call(question, system_message, history=history)

    def get_graph_url(self, question, history):
        system_message = f"""
        Please attempt to extract the 'GraphCall' from the question. If either of these details is not explicitly defined within the question, leave the corresponding field empty. 
        If you want to skip this step, you can include the phrase 'UserWantSkip' in your input.

        Try to complete the graph call if this is shorten. Here are some examples:
        # Example 1
        Input:
        "Can you run the following graph call and export the results in csv. Graph call: https://graph.microsoft.com/beta/me"
        Output:
        # Answer
        GraphCall: me
        UserWantSkip: 

        # Example 2
        Input:
        "Can you run the following graph call applications?$count=true"
        Output:
        # Answer
        GraphCall: applications?$count=true
        UserWantSkip: 

        Always respond following the structure:        
            # Answer
            GraphCall: 
            UserWantSkip: 
        """
        response =  self.invoke_gpt_call(question, system_message, history=history)
        
        # Extracting values using regular expressions
        graph_call_match = re.search(r'GraphCall:\s*(.*?)(?=UserWantSkip:|$)', response, re.DOTALL | re.IGNORECASE)
        user_want_skip_match = re.search(r'UserWantSkip:\s*(.*?)\s*$', response, re.DOTALL | re.IGNORECASE)
        
        graph_call = graph_call_match.group(1).strip() if graph_call_match else None
        user_want_skip = True if user_want_skip_match and user_want_skip_match.group(1).strip() else False

        return {
            "graph_call": graph_call,
            "user_want_skip": user_want_skip
        }
    
    def run_graph_call(self, question, graph_call, history):
        response = self.get_graph_call_custom(graph_call, value=False)
        
        system_message = f"""
        If the user asks about executing a graph call, inform them: 'I don't have the ability to make live API calls by ma own. However, based on the provided data from the executed call, here's the result:'. Then, answer the question of the user based on the "Graph result".

        # Graph result
        {response}
        """
        return self.invoke_gpt_call(question, system_message, history=history)