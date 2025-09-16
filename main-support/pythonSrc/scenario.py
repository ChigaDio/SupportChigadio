import sys
import os
import json
from enum import Enum
SCENARIO_DATA = 'scenario-data'
SCENARIO_ROLE =  os.path.join(SCENARIO_DATA, 'scenario-role')
SCENARIO_CONDITIONS_DATA = os.path.join(SCENARIO_DATA, 'scenario-conditions-data')
SCENARIO_EVENT = os.path.join(SCENARIO_DATA, 'scenario-event-data')

def generate_scenario_folder(parent_path : str):
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA)):
        os.makedirs(os.path.join(parent_path, SCENARIO_DATA))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_ROLE)):
        os.makedirs(os.path.join(parent_path, SCENARIO_ROLE))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_CONDITIONS_DATA)):
        os.makedirs(os.path.join(parent_path, SCENARIO_CONDITIONS_DATA))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_EVENT)):
        os.makedirs(os.path.join(parent_path, SCENARIO_EVENT))

def generate_base_script_file(parent_path : str):
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenearioRoleData.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;

namespace GameCore.Scenario
{
    public class BaseScenarioRoleData
    {
        public ScenarioRoleID RoleID { get; private set; }
        public int ScenarioGroupID { get; private set; }
        public int ScenarioSubGroupID { get; private set; }
        public int ScenarioSeekPos { get; set; } = -1;

        public virtual void ReadBinary(BinaryReader reader)
        {
            RoleID = (ScenarioRoleID)reader.ReadInt32();
            ScenarioGroupID = reader.ReadInt32();
            ScenarioSubGroupID = reader.ReadInt32();
        }
    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenearioRoleData.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
    
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseOrigintScenarioRoleAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;
using System.IO;
namespace GameCore.Scenario
{
    public  class BaseOrigintScenarioRoleAction
    {
        public bool IsCompleted { get; protected set; } = false;
        public virtual void ReadBinary(BinaryReader reader);
        public virtual void OnInitialize()
        {
            IsCompleted = false;
        }
        public virtual void OnExecute()
        {
            // Implement action logic here
        }
        public virtual void OnFinalize()
        {
            // Implement cleanup logic here
        }
    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseOrigintScenarioRoleActionbstractScenarioRoleAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseGeneralScenarioRoleAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;
using System.IO;
namespace GameCore.Scenario
{
    public  class BaseGeneralScenarioRoleAction<T> : BaseOrigintScenarioRoleAction where T : BaseScenarioRoleData
    {
        public T RoleData { get; private set; }

        public BaseGeneralScenarioRoleAction(T roleData) : base()
        {
            RoleData = roleData;
        }


        public virtual void OnInitialize()
        {
            base.OnInitialize();
        }
    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseGeneralScenarioRoleAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;

namespace GameCore.Scenario
{
    public class BaseScenarioRoleAction<T> : BaseGeneralScenarioRoleAction<T> where T : BaseScenarioRoleData
    {

        public BaseScenarioRoleAction(T roleData) : base(roleData);

        public override virtual void OnInitialize()
        {
            base.OnInitialize();
        }



    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleBranchAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;

namespace GameCore.Scenario
{
    public class BaseScenarioRoleBranchAction<T> : BaseGeneralScenarioRoleAction<T> where T : BaseScenarioRoleData
    {


        public BaseScenarioRoleBranchAction(T roleData) : base(roleData);

        public virtual void OnInitialize()
        {
            base.OnInitialize();
        }


    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleBranchAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

