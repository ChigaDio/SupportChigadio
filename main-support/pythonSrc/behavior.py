
import json
import math
import os
import socket
import struct
import sys
import tkinter as tk
from tkinter import filedialog
import shutil
import uuid
from flask import jsonify

import pythonSrc.trash as trash

# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    

# ディレクトリパスをプロジェクトルート基準に設定
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
BEHAVIOR_DATA = os.path.join(DATA_DIR, "behavior_data")

def init(data_dir):
    global DATA_DIR, BEHAVIOR_DATA
    DATA_DIR = os.path.abspath(data_dir)
    BEHAVIOR_DATA = os.path.join(DATA_DIR, "behavior_data")

def generate_csharp(path,code_str):
    if not os.path.exists(path):
        with open(path,"w",encoding="utf-8") as f:
            f.write(code_str)

def generate_base():
    if not os.path.exists(BEHAVIOR_DATA):
        os.mkdir(BEHAVIOR_DATA)
        
    code_str = """
// File: CooldownNode.cs
using System;

namespace GameCore.Behavior
{
    public class ActionNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {


        public ActionNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Leaf;
            NodeID = BehaviorNodeID.Action;   
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {

            return BehaviorResultStatus.Success;
        }

        public override void OnReset(TBlackboard blackboard)
        {
        }
        
    }
}
        """
    generate_csharp(os.path.join(BEHAVIOR_DATA,"ActionNode.cs"),code_str)
    code_str = """
using System;
namespace GameCore.Behavior
{
    public class BaseBehaviorBlackboard<T, TEnum> 
    where T : BaseBehaviorBlackboard<T,TEnum>, new()
    where TEnum : struct, Enum

    {
        protected readonly Utils.FastEnumBitFlags<TEnum> Flags = new Utils.FastEnumBitFlags<TEnum>();
        public BaseBehaviorBlackboard()
        {
            Flags = new Utils.FastEnumBitFlags<TEnum>();
        }
        public void OnInit(Action<T> action = null)
        {
            action?.Invoke((T)this); // T にキャストして渡す
        }

        public void OnReset(Action<T> action = null)
        {
            action?.Invoke((T)this);
        }

        // ================ フラグ操作（委譲） ================
        public bool IsFlagSet(TEnum flag) => Flags.IsSet(flag);
        public void SetFlag(TEnum flag) => Flags.Set(flag);
        public void ClearFlag(TEnum flag) => Flags.Clear(flag);
        public void ToggleFlag(TEnum flag) => Flags.Toggle(flag);
        public void XORFlag(TEnum flag, bool value) => Flags.XORBit(flag, value);
        public void ANDFlag(TEnum flag, bool value) => Flags.ANDBit(flag, value);
        public void ORFlag(TEnum flag, bool value) => Flags.ORBit(flag, value);
        public void ClearAllFlags() => Flags.ClearAll();
        public void SetAllFlags() => Flags.SetAll();
    }


}

"""
    generate_csharp(os.path.join(BEHAVIOR_DATA,"BaseBehaviorBlackboard.cs"),code_str)
    code_str = """

using System;
using System.Collections.Generic;

namespace GameCore.Behavior
{
    public abstract class BaseBehaviorNode<TBlackboard, TEnum> : OriginBehaviorNode
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public BehaviorNodeCategory NodeCategory { get; protected set; }

        public BehaviorNodeID NodeID { get; protected set; }
        public TEnum CustomNodeID { get; protected set; }

        public BehaviorResetTypeID ResetTypeID { get; protected set; }

        protected List<BaseBehaviorNode<TBlackboard, TEnum>> children = new();

        public IReadOnlyList<BaseBehaviorNode<TBlackboard, TEnum>> Children => children;

        public BaseBehaviorNode(TEnum valueCustomNodeID,BehaviorResetTypeID resetType)
        {
            CustomNodeID = valueCustomNodeID;
            ResetTypeID = resetType;
        }

        public abstract void OnInit(TBlackboard blackboard);

        public abstract BehaviorResultStatus OnTick(TBlackboard blackboard);

        public abstract void OnReset(TBlackboard blackboard);

        public void CheckResetExecute(BaseBehaviorNode<TBlackboard, TEnum> child,TBlackboard blackboard)
        {
            if (child == null) return;
            if (child.ResetTypeID == BehaviorResetTypeID.None) return;
            
            blackboard.XORFlag(child.CustomNodeID,true);
            var check = blackboard.IsFlagSet(child.CustomNodeID);
            if (check == false) return;
            

            if (child.ResetTypeID == BehaviorResetTypeID.THIS_RESET)
            {
                this.OnReset(blackboard);
            }
            else if (child.ResetTypeID == BehaviorResetTypeID.THIS_CHILD_RESET_ALL)
            {
                this.OnAllReset(blackboard);
            }
            else if (child.ResetTypeID == BehaviorResetTypeID.CHILD_FIRST_RESET)
            {
                child.OnReset(blackboard);
            }
            else if(child.ResetTypeID == BehaviorResetTypeID.CHILD_FIRST_RESET)
            {
                child.OnAllReset(blackboard);
            }

            
        }
        public void OnAllReset(TBlackboard blackboard)
        {
            OnReset(blackboard);
            foreach (var child in Children)
                child.OnAllReset(blackboard);
        }

        public void AddChild(BaseBehaviorNode<TBlackboard, TEnum> child)
        {
            if (child != null)
                children.Add(child);
        }

        public void AddChildren(List<BaseBehaviorNode<TBlackboard, TEnum>> valueChildren)
        {
            if (valueChildren != null)
                children.AddRange(valueChildren);
        }

        public void SetChildren(List<BaseBehaviorNode<TBlackboard, TEnum>> valueChildren)
        {
            children = valueChildren ?? new();
        }

        public void SetChild(BaseBehaviorNode<TBlackboard, TEnum> child)
        {
            children = child != null ? new List<BaseBehaviorNode<TBlackboard, TEnum>> { child } : new();
        }
    }
}



"""
    generate_csharp(os.path.join(BEHAVIOR_DATA,"BaseBehaviorNode.cs"),code_str)
        # -------------------------------------------------
    # 4. ConditionNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class ConditionNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public ConditionNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Leaf;
            NodeID = BehaviorNodeID.Condition;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            bool result = Compare(blackboard);
            return result ? BehaviorResultStatus.Success : BehaviorResultStatus.Failure;
        }

        public override void OnReset(TBlackboard blackboard) { }

        protected virtual bool Compare(TBlackboard blackboard)
        {
            return false;
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "ConditionNode.cs"), code_str)

    # -------------------------------------------------
    # 5. SequenceNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class SequenceNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public SequenceNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Composite;
            NodeID = BehaviorNodeID.Sequence;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            foreach (var child in Children)
            {
                CheckResetExecute(child,blackboard);
                var result = child.OnTick(blackboard);
                if (result != BehaviorResultStatus.Success)
                    return result;
            }
            return BehaviorResultStatus.Success;
        }

        public override void OnReset(TBlackboard blackboard)
        {
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "SequenceNode.cs"), code_str)

    # -------------------------------------------------
    # 6. SelectorNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class SelectorNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public SelectorNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Composite;
            NodeID = BehaviorNodeID.Selector;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            foreach (var child in Children)
            {
                CheckResetExecute(child,blackboard);
                var result = child.OnTick(blackboard);
                if (result == BehaviorResultStatus.Success)
                    return BehaviorResultStatus.Success;
            }
            return BehaviorResultStatus.Failure;
        }

        public override void OnReset(TBlackboard blackboard)
        {
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "SelectorNode.cs"), code_str)

    # -------------------------------------------------
    # 7. ParallelNode.cs
    # -------------------------------------------------
    code_str = """
using System;
using System.Linq;

namespace GameCore.Behavior
{
    public enum ParallelPolicyID
    {
        ALL,
        ANY
    }

    public class ParallelNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public ParallelPolicyID SuccessPolicy { get; set; } = ParallelPolicyID.ALL;
        public ParallelPolicyID FailurePolicy { get; set; } = ParallelPolicyID.ANY;

        public ParallelNode(TEnum customNodeID, ParallelPolicyID valueSuccessPolicy, ParallelPolicyID valueFailurePolicy,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            SuccessPolicy = valueSuccessPolicy;
            FailurePolicy = valueFailurePolicy;
            
            NodeCategory = BehaviorNodeCategory.Composite;
            NodeID = BehaviorNodeID.Parallel;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            var results = Children.Select(c =>
            {
                CheckResetExecute(c,blackboard);
                var result = c.OnTick(blackboard);
                return result;
            }).ToList();

            bool allSuccess = results.All(r => r == BehaviorResultStatus.Success);
            bool anySuccess = results.Any(r => r == BehaviorResultStatus.Success);
            bool allFailure = results.All(r => r == BehaviorResultStatus.Failure);
            bool anyFailure = results.Any(r => r == BehaviorResultStatus.Failure);

            if (SuccessPolicy == ParallelPolicyID.ALL && allSuccess) return BehaviorResultStatus.Success;
            else if (SuccessPolicy == ParallelPolicyID.ANY && anySuccess) return BehaviorResultStatus.Success;
            if (FailurePolicy == ParallelPolicyID.ALL && allFailure) return BehaviorResultStatus.Failure;
            else if (FailurePolicy == ParallelPolicyID.ANY && anyFailure) return BehaviorResultStatus.Failure;

            return BehaviorResultStatus.InProgress;
        }

        public override void OnReset(TBlackboard blackboard)
        {
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "ParallelNode.cs"), code_str)

    # -------------------------------------------------
    # 8. RaceNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class RaceNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        private bool _finished = false;

        public RaceNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Composite;
            NodeID = BehaviorNodeID.Race;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (_finished) return BehaviorResultStatus.Success;

            foreach (var child in Children)
            {
                CheckResetExecute(child,blackboard);
                var result = child.OnTick(blackboard);
                if (result == BehaviorResultStatus.Success || result == BehaviorResultStatus.Failure)
                {
                    _finished = true;
                    return result;
                }
            }
            return BehaviorResultStatus.InProgress;
        }

        public override void OnReset(TBlackboard blackboard)
        {
            _finished = false;
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "RaceNode.cs"), code_str)

    # -------------------------------------------------
    # 9. RepeaterNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class RepeaterNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public int Count { get; set; } = 3;
        private int _current = 0;

        public RepeaterNode(TEnum customNodeID, int valueCount,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            Count = valueCount;
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.Repeater;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count == 0) return BehaviorResultStatus.Failure;
            if (_current >= Count) return BehaviorResultStatus.Success;
            CheckResetExecute(Children[0],blackboard);
            var result = Children[0].OnTick(blackboard);
            if (result == BehaviorResultStatus.Success || result == BehaviorResultStatus.Failure)
                _current++;

            return _current >= Count ? BehaviorResultStatus.Success : BehaviorResultStatus.InProgress;
        }

        public override void OnReset(TBlackboard blackboard)
        {
            _current = 0;
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "RepeaterNode.cs"), code_str)

    # -------------------------------------------------
    # 10. DelayNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class DelayNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public float Seconds { get; set; } = 1.0f;
        private float _timer = 0f;
        private bool _started = false;

        public DelayNode(TEnum customNodeID, float valueSeconds,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.Delay;
            Seconds = valueSeconds;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count == 0) return BehaviorResultStatus.Failure;

            if (!_started)
            {
                _timer = 0f;
                _started = true;
            }

            _timer += UnityEngine.Time.deltaTime;
            if (_timer < Seconds)
                return BehaviorResultStatus.InProgress;
            CheckResetExecute(Children[0],blackboard);
            var result = Children[0].OnTick(blackboard);
            _started = false;
            return result;
        }

        public override void OnReset(TBlackboard blackboard)
        {
            _timer = 0f;
            _started = false;
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "DelayNode.cs"), code_str)

    # -------------------------------------------------
    # 11. FailerNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class FailerNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public FailerNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.Failer;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count > 0)
            {
                CheckResetExecute(Children[0],blackboard);
                Children[0].OnTick(blackboard);
            }
            return BehaviorResultStatus.Failure;
        }

        public override void OnReset(TBlackboard blackboard)
        {
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "FailerNode.cs"), code_str)

    # -------------------------------------------------
    # 12. LimiterNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class LimiterNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public int Max { get; set; } = 3;
        private int _current = 0;

        public LimiterNode(TEnum customNodeID, int valueMax,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            Max = valueMax;
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.Limiter;
        }

        public override void OnInit(TBlackboard blackboard)
        {

            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count == 0 || _current >= Max) return BehaviorResultStatus.Failure;
            _current++;
            CheckResetExecute(Children[0],blackboard);
            return Children[0].OnTick(blackboard);
        }

        public override void OnReset(TBlackboard blackboard)
        {
            _current = 0;
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "LimiterNode.cs"), code_str)

    # -------------------------------------------------
    # 13. RepeatUntilSuccessNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class RepeatUntilSuccessNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public RepeatUntilSuccessNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.RepeatUntilSuccess;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count == 0) return BehaviorResultStatus.Failure;
            CheckResetExecute(Children[0],blackboard);
            var result = Children[0].OnTick(blackboard);
            return result == BehaviorResultStatus.Success ? BehaviorResultStatus.Success : BehaviorResultStatus.InProgress;
        }

        public override void OnReset(TBlackboard blackboard)
        {
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "RepeatUntilSuccessNode.cs"), code_str)

    # -------------------------------------------------
    # 14. InverterNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class InverterNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public InverterNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.Inverter; 
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count == 0) return BehaviorResultStatus.Failure;
            CheckResetExecute(Children[0],blackboard);
            var result = Children[0].OnTick(blackboard);
            return result == BehaviorResultStatus.Success ? BehaviorResultStatus.Failure :
                   result == BehaviorResultStatus.Failure ? BehaviorResultStatus.Success : result;
        }

        public override void OnReset(TBlackboard blackboard)
        {
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "InverterNode.cs"), code_str)

    # -------------------------------------------------
    # 15. CooldownNode.cs
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class CooldownNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public float Seconds { get; set; } = 1.0f;
        private float _timer = 0f;
        private bool _inCooldown = false;
        private BehaviorResultStatus _lastResult = BehaviorResultStatus.Success;

        public CooldownNode(TEnum customNodeID, float valueSeconds,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            Seconds = valueSeconds;
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.Cooldown;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count == 0) return BehaviorResultStatus.Failure;

            if (_inCooldown)
            {
                _timer += UnityEngine.Time.deltaTime;
                if (_timer >= Seconds)
                {
                    _inCooldown = false;
                    _timer = 0f;
                }
                return _lastResult;
            }
            CheckResetExecute(Children[0],blackboard);
            var result = Children[0].OnTick(blackboard);
            if (result == BehaviorResultStatus.Success || result == BehaviorResultStatus.Failure)
            {
                _inCooldown = true;
                _timer = 0f;
                _lastResult = result;
            }
            return result;
        }

        public override void OnReset(TBlackboard blackboard)
        {
            _timer = 0f;
            _inCooldown = false;
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "CooldownNode.cs"), code_str)

    # -------------------------------------------------
    # 16. TimeoutNode.cs（すでにドキュメントに含まれる）
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class TimeoutNode<TBlackboard, TEnum> : BaseBehaviorNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public float Seconds { get; set; } = 5.0f;
        private float _timer = 0f;
        private bool _started = false;

        public TimeoutNode(TEnum customNodeID, float valueSeconds,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            Seconds = valueSeconds;
            NodeCategory = BehaviorNodeCategory.Decorator;
            NodeID = BehaviorNodeID.Timeout;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }

        public override BehaviorResultStatus OnTick(TBlackboard blackboard)
        {
            if (Children.Count == 0) return BehaviorResultStatus.Failure;

            if (!_started)
            {
                _timer = 0f;
                _started = true;
            }

            _timer += UnityEngine.Time.deltaTime;
            CheckResetExecute(Children[0],blackboard);
            var result = Children[0].OnTick(blackboard);
            if (result != BehaviorResultStatus.InProgress)
            {
                _started = false;
                return result;
            }

            if (_timer >= Seconds)
            {
                _started = false;
                return BehaviorResultStatus.Timeout;
            }

            return BehaviorResultStatus.InProgress;
        }

        public override void OnReset(TBlackboard blackboard)
        {
            _timer = 0f;
            _started = false;;
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "TimeoutNode.cs"), code_str)
    

    # -------------------------------------------------
    # 17. 列挙型：BehaviorNodeID.cs
    # -------------------------------------------------
    code_str = """
namespace GameCore.Behavior
{
    public enum BehaviorNodeID
    {
        None = 0,
        Root,
        Sequence,
        Selector,
        Parallel,
        Race,
        Repeater,
        Delay,
        Timeout,
        Inverter,
        Failer,
        Limiter,
        RepeatUntilSuccess,
        Cooldown,
        Action,
        Condition,
        BlackboardCondition
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BehaviorNodeID.cs"), code_str)

    # -------------------------------------------------
    # 18. 列挙型：BehaviorNodeCategory.cs
    # -------------------------------------------------
    code_str = """
namespace GameCore.Behavior
{
    public enum BehaviorNodeCategory
    {
        Composite,
        Decorator,
        Leaf
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BehaviorNodeCategory.cs"), code_str)

    # -------------------------------------------------
    # 19. 列挙型：BehaviorResultStatus.cs
    # -------------------------------------------------
    code_str = """
namespace GameCore.Behavior
{
    public enum BehaviorResultStatus
    {
        Success = 0,
        Failure = 1,
        InProgress = 2,
        Canceled = 3,
        Timeout = 4,
        Unknown = 5
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BehaviorResultStatus.cs"), code_str)

    # -------------------------------------------------
    # 20. OriginBehaviorNode.cs（基底）
    # -------------------------------------------------
    code_str = """
namespace GameCore.Behavior
{
    public abstract class OriginBehaviorNode
    {
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "OriginBehaviorNode.cs"), code_str)

    # -------------------------------------------------
    # 21. BaseBehaviorBlackboard.cs（修正版）
    # -------------------------------------------------
    code_str = """
using System;
namespace GameCore.Behavior
{
    public class BaseBehaviorBlackboard<T, TEnum> 
    where T : BaseBehaviorBlackboard<T,TEnum>, new()
    where TEnum : struct, Enum

    {
        protected readonly Utils.FastEnumBitFlags<TEnum> Flags = new Utils.FastEnumBitFlags<TEnum>();
        public BaseBehaviorBlackboard()
        {
            Flags = new Utils.FastEnumBitFlags<TEnum>();
        }
        public void OnInit(Action<T> action = null)
        {
            action?.Invoke((T)this); // T にキャストして渡す
        }

        public void OnReset(Action<T> action = null)
        {
            action?.Invoke((T)this);
        }

        // ================ フラグ操作（委譲） ================
        public bool IsFlagSet(TEnum flag) => Flags.IsSet(flag);
        public void SetFlag(TEnum flag) => Flags.Set(flag);
        public void ClearFlag(TEnum flag) => Flags.Clear(flag);
        public void ToggleFlag(TEnum flag) => Flags.Toggle(flag);
        public void XORFlag(TEnum flag, bool value) => Flags.XORBit(flag, value);
        public void ANDFlag(TEnum flag, bool value) => Flags.ANDBit(flag, value);
        public void ORFlag(TEnum flag, bool value) => Flags.ORBit(flag, value);
        public void ClearAllFlags() => Flags.ClearAll();
        public void SetAllFlags() => Flags.SetAll();
    }


}

"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BaseBehaviorBlackboard.cs"), code_str)

    # -------------------------------------------------
    # 22. BaseBehaviorNode.cs（完全版）
    # -------------------------------------------------
    code_str = """
using System;
using System.Collections.Generic;

namespace GameCore.Behavior
{
    public abstract class BaseBehaviorNode<TBlackboard, TEnum> : OriginBehaviorNode
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public BehaviorNodeCategory NodeCategory { get; protected set; }

        public BehaviorNodeID NodeID { get; protected set; }
        public TEnum CustomNodeID { get; protected set; }

        public BehaviorResetTypeID ResetTypeID { get; protected set; }

        protected List<BaseBehaviorNode<TBlackboard, TEnum>> children = new();

        public IReadOnlyList<BaseBehaviorNode<TBlackboard, TEnum>> Children => children;

        public BaseBehaviorNode(TEnum valueCustomNodeID,BehaviorResetTypeID resetType)
        {
            CustomNodeID = valueCustomNodeID;
            ResetTypeID = resetType;
        }

        public abstract void OnInit(TBlackboard blackboard);

        public abstract BehaviorResultStatus OnTick(TBlackboard blackboard);

        public abstract void OnReset(TBlackboard blackboard);

        public void CheckResetExecute(BaseBehaviorNode<TBlackboard, TEnum> child,TBlackboard blackboard)
        {
            if (child == null) return;
            if (child.BehaviorResetTypeID == BehaviorResetTypeID.None) return;
            
            blackboard.XORFlag(result.CustomNodeID,true);
            var check = blackboard.IsFlagSet(result.CustomNodeID);
            if (check == false) return;
            

            if (child.BehaviorResetTypeID == BehaviorResetTypeID.THIS_RESET)
            {
                this.OnReset(blackboard);
            }
            else if (hild.BehaviorResetTypeID == BehaviorResetTypeID.THIS_CHILD_RESET_ALL)
            {
                this.OnAllReset(blackboard);
            }
            else if (hild.BehaviorResetTypeID == BehaviorResetTypeID.CHILD_FIRST_RESET)
            {
                child.OnReset(blackboard);
            }
            else if(hild.BehaviorResetTypeID == BehaviorResetTypeID.CHILD_FIRST_RESET)
            {
                child.OnAllReset(blackboard);
            }

            
        }
        public void OnAllReset(TBlackboard blackboard)
        {
            OnReset();
            foreach (var child in Children)
                child.OnAllReset();
        }

        public void AddChild(BaseBehaviorNode<TBlackboard, TEnum> child)
        {
            if (child != null)
                children.Add(child);
        }

        public void AddChildren(List<BaseBehaviorNode<TBlackboard, TEnum>> valueChildren)
        {
            if (valueChildren != null)
                children.AddRange(valueChildren);
        }

        public void SetChildren(List<BaseBehaviorNode<TBlackboard, TEnum>> valueChildren)
        {
            children = valueChildren ?? new();
        }

        public void SetChild(BaseBehaviorNode<TBlackboard, TEnum> child)
        {
            children = child != null ? new List<BaseBehaviorNode<TBlackboard, TEnum>> { child } : new();
        }
    }
}

"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BaseBehaviorNode.cs"), code_str)

    # -------------------------------------------------
    # 23. BaseBehaviorTree.cs（ツリー本体）
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public abstract class BaseBehaviorTree<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public TBlackboard Blackboard { get; private set; } = new();
        public BaseBehaviorNode<TBlackboard, TEnum> Root { get; protected set; }

        public void SetRoot(BaseBehaviorNode<TBlackboard, TEnum> root) => Root = root;

        public abstract void OnInit(Action<TBlackboard> action = null,TBlackboard blackboard = null);
        public abstract BehaviorResultStatus Tick();
        public abstract void OnReset(Action<TBlackboard> action = null);
        public void SetBlackboard(TBlackboard blackboard) => Blackboard = blackboard;
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BaseBehaviorTree.cs"), code_str)

    # -------------------------------------------------
    # 24. BlackboardConditionNode.cs（ブラックボード条件）
    # -------------------------------------------------
    code_str = """
using System;

namespace GameCore.Behavior
{
    public class BlackboardConditionNode<TBlackboard, TEnum> : ConditionNode<TBlackboard, TEnum>
        where TBlackboard : BaseBehaviorBlackboard<TBlackboard,TEnum>, new()
        where TEnum : struct, Enum
    {
        public BlackboardConditionNode(TEnum customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {
            NodeCategory = BehaviorNodeCategory.Leaf;
            NodeID = BehaviorNodeID.BlackboardCondition;
        }

        public override void OnInit(TBlackboard blackboard)
        {
            OnReset(blackboard);
        }
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BlackboardConditionNode.cs"), code_str)


    # -------------------------------------------------
    # 25. BehaviorResetTypeID.cs
    # -------------------------------------------------
    code_str = """
namespace GameCore.Behavior
{
    public enum BehaviorResetTypeID
    {
        None,
        THIS_RESET,
        THIS_CHILD_RESET_ALL,
        CHILD_FIRST_RESET,
        
    }
}
"""
    generate_csharp(os.path.join(BEHAVIOR_DATA, "BehaviorResetTypeID.cs"), code_str)




    print("すべての基底ノードを生成しました。")


def get_behavior_data():
    behavior_dir = os.path.join(DATA_DIR, BEHAVIOR_DATA)
    if not os.path.exists(behavior_dir):
        os.makedirs(behavior_dir)
    behaviors = []
    for folder in os.listdir(behavior_dir):
        folder_path = os.path.join(behavior_dir, folder)
        if os.path.isdir(folder_path):
            behaviors.append({'id': folder, 'name': folder})
    return jsonify(behaviors)


def add_behavior(request):
    data = request.json
    name = data.get('name')
    if not name or not name.strip():
        return jsonify({'error': 'Invalid name'}), 400
    
    behavior_dir = os.path.join(DATA_DIR, BEHAVIOR_DATA, name)
    if os.path.exists(behavior_dir):
        return jsonify({'error': 'Already exists'}), 400
    
    os.makedirs(behavior_dir)
    
    # 正しい初期構造（root を nodes に入れる！）
    init_data = {
        "root": "root",
        "nodes": {
            "root": {
                "id": "root",
                "type": "root",
                "label": "Root",
                "order": 0,
                "children": []
            }
        },
        "blackboard": {},
        "customNodes": []
    }
    
    with open(os.path.join(behavior_dir, f"{name}.json"), 'w', encoding='utf-8') as f:
        json.dump(init_data, f, indent=2, ensure_ascii=False)
    
    return jsonify({'message': 'Created', 'data': {'id': name}})

def delete_behavior(name):
    behavior_dir = os.path.join(DATA_DIR, BEHAVIOR_DATA, name)
    if os.path.exists(behavior_dir):
        trash.move_to_trash('behavior_data', name, behavior_dir)
        return jsonify({'message': 'Deleted'})
    return jsonify({'error': 'Not found'}), 404


def get_behavior_detail(name):
    behavior_path = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"{name}.json")
    if not os.path.exists(behavior_path):
        return jsonify({'error': 'Not found'}), 404
    
    with open(behavior_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 古い形式（root が nodes 外）→ 新形式に変換
    if 'root' in data and isinstance(data['root'], dict):
        root_obj = data['root']
        data['root'] = 'root'
        data['nodes'] = data.get('nodes', {})
        data['nodes']['root'] = {
            "id": "root",
            "type": root_obj.get('type', 'sequence').lower(),
            "label": root_obj.get('label', 'Root'),
            "order": 0,
            "children": root_obj.get('children', [])
        }
    
    return jsonify(data)


def save_behavior_detail(name,request):
    data = request.json
    behavior_path = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"{name}.json")
    
    # root ノードを nodes に入れる
    root_data = data.get('nodes', {}).get('root',{})
    nodes = data.get('nodes', {})
    root_id = 'root'
    
    nodes[root_id] = {
        "id": root_id,
        "type": root_data.get('type', 'root'),
        "label": root_data.get('label', 'Root'),
        "order": 0,
        "children": root_data.get('children', [])
    }
    
    # 他のノードも children 配列保証
    for node_id, node in nodes.items():
        if node_id != root_id:
            if 'children' not in node:
                node['children'] = []
    
    save_data = {
        "root": root_id,
        "nodes": nodes,
        "blackboard": data.get('blackboard', {}),
        "customNodes": data.get('customNodes', [])
    }
    
    with open(behavior_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    
    return jsonify({'message': 'Saved'})

def generate_behavior_code(name,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data):
    behavior_path = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"{name}.json")
    if not os.path.exists(behavior_path):
        return jsonify({'error': 'Not found'}), 404
    # ここにC#コード生成ロジック（後で実装）
    with open(behavior_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    
    generate_custom_node(data,name)
    generate_custom_condition(data,name,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
    generate_custom_blackboard(data,name,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
    generate_behavior_tree(data,name)
    return jsonify({'message': 'コード生成完了'})

def generate_custom_id_code(data, name):
    nodes = data.get("nodes", {})
    root_id = data.get("root")
    result = []  # enum 用のエントリ
    id_map = {}  # node_id → enum_id のマッピング（後で再利用）

    def traverse(node_id, parent_label="None", depth=0, child_index=0):
        node = nodes.get(node_id)
        if not node:
            return

        label = node.get("label", node_id)
        order = node.get("order", depth)

        # 子ノードを走査
        children = node.get("children", [])
        for index, child_id in enumerate(children):
            child = nodes.get(child_id)
            if not child:
                continue

            child_label = child.get("label", child_id)
            child_order = child.get("order", order + 1)

            # 正確な enum ID 生成（A_B_C_D 形式）
            enum_id = f"{child_label}_{label}_{child_order}_{index}"
            result.append(f"{enum_id},")
            id_map[child_id] = enum_id  # マッピング保存

            traverse(child_id, label, child_order, index)

    traverse(root_id)
    enum_entries = "\n      ".join(result)

    code_str = f"""namespace GameCore.Behavior
{{
  public enum {name}BehaviorID
  {{
      None = 0,
      {enum_entries}
      Max
  }}
}}"""

    output_path = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"{name}BehaviorID.cs")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(code_str)

    return id_map  # マッピングを返す



#カスタムノード作成
def generate_custom_node(data,name):
    
    customNodes = data.get("customNodes",[])
    
    code_str = ""
    add_str = ""
    base_class = ""
    init_id = ""
    class_str = ""
    tick_return = ""
    for node in customNodes:
        add_str = ""
        path_add = node['name']
        if node['type'] == "action":
            path_add += "Action"
            class_str = f"{name}{node['name']}ActionNode"
            base_class = f"{name}{node['name']}ActionNode : ActionNode<{name}BehaviorBlackboard,{name}BehaviorID>"
            init_id = "Action"
            tick_return = "return BehaviorResultStatus.Success;"
        else:
            path_add += "Condition"
            class_str = f"{name}{node['name']}ConditionNode"
            base_class = f"{name}{node['name']}ConditionNode : ConditionNode<{name}BehaviorBlackboard,{name}BehaviorID>"
            init_id = "BlackboardCondition"
            tick_return = "bool result = Compare(blackboard);\n            return result ? BehaviorResultStatus.Success : BehaviorResultStatus.Failure;"
        path = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"{name}{node['name']}")
        path += "Action.cs"  if node['type'] == "action" else "Condition.cs"
        if node['type'] == "condition":
            add_str = f"""
        protected override bool Compare({name}BehaviorBlackboard blackboard)
        {{
            return true;
        }}
        """
        code_str = f"""
namespace GameCore.Behavior
{{
    public class {base_class}
    {{
        public {class_str}({name}BehaviorID customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {{
        }}

        public override void OnInit({name}BehaviorBlackboard blackboard)
        {{
            OnReset(blackboard);
        }}

        public override BehaviorResultStatus OnTick({name}BehaviorBlackboard blackboard)
        {{

            {tick_return}
        }}

        public override void OnReset({name}BehaviorBlackboard blackboard)
        {{
            base.OnReset(blackboard);
        }}
        
        {add_str}
    }}
    
}}
    """
        if not os.path.exists(path):
            with open(path,"w", encoding="utf-8") as f:
                f.write(code_str)
        
        
        
def generate_custom_condition(data,name,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data):
    nodes = data.get("nodes", {})
    root_id = data.get("root")

    result = []  # enum用
    blackboard_nodes = []  # blackboard型専用

    def traverse(node_id, parent_label="None", depth=0, child_index=0):
        node = nodes.get(node_id)
        if not node:
            return

        label = node.get("label", node_id)
        order = node.get("order", depth)
        node_type = node.get("type", "")
        parent_label_str = parent_label or "None"

        # このノード自身のID（A_D_B_C形式）
        node_enum_id = f"{label}_{parent_label_str}_{order}_{child_index}"

        # blackboard系だけ抽出
        if node_type.startswith("blackboard"):
            blackboard_nodes.append({
                "id": node_enum_id,
                "label": label,
                "type": node_type,
                "order": order,
                "parent": parent_label_str
            })

        # 子ノードを走査
        children = node.get("children", [])
        for index, child_id in enumerate(children):
            child = nodes.get(child_id)
            if not child:
                continue
            child_label = child.get("label", child_id)
            child_order = child.get("order", order + 1)
            entry = f"{child_label}_{label}_{child_order}_{index},"
            result.append(entry)
            traverse(child_id, label, child_order, index)

    traverse(root_id)
    
    code_str = ""
    id_str = ""
    for blackboard in blackboard_nodes:
        id_str += f"""
                {blackboard["id"]} => Compare_{blackboard["id"]}(blackboard),
        """
        code_str += f"""
        protected virtual bool Compare_{blackboard["id"]}({name}BehaviorBlackboard blackboard)
        {{
            return false;
        }}
        """
    id_str += """
                _ => false
    """
    
    path_base = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"Base{name}BlackboardConditionNode.cs")
    path = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"{name}BlackboardConditionNode.cs")
    
    with open(path_base,"w", encoding="utf-8") as f:
        base_str = f"""
using System;
using System.Collections.Generic;

namespace GameCore.Behavior
{{
    public class Base{name}BlackboardConditionNode : BlackboardConditionNode<{name}BehaviorBlackboard,{name}BehaviorID>
    {{
        public Base{name}BlackboardConditionNode({name}BehaviorID customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {{
            NodeCategory = BehaviorNodeCategory.Leaf;
            NodeID = BehaviorNodeID.BlackboardCondition;  
        }}

        public override void OnInit({name}BehaviorBlackboard blackboard)
        {{
            OnReset(blackboard);
        }}


        public override void OnReset({name}BehaviorBlackboard blackboard) {{ }}

        protected override bool Compare({name}BehaviorBlackboard blackboard)
        {{
            var result = CustomNodeID switch
            {{
{id_str}
            }};
            return result;
        }}
        
{code_str}
    }}
}}
"""
        f.write(base_str)
    code_str = code_str.replace("virtual", "override")
    
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if not os.path.exists(path):
        with open(path,"w", encoding="utf-8") as fp:
            base_str = f"""
using System;
using System.Collections.Generic;

namespace GameCore.Behavior
{{
    public class {name}BlackboardConditionNode : Base{name}BlackboardConditionNode
    {{
        public {name}BlackboardConditionNode({name}BehaviorID customNodeID,BehaviorResetTypeID resetType) : base(customNodeID,resetType)
        {{
            
        }}

        
{code_str}
    }}
}}
"""
            fp.write(base_str)
    
    


def generate_custom_blackboard(data,name,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data):
    blackboardData = data["blackboard"]
    
    TYPE_MAP = {
    'int': {'pack': 'i', 'cs_read': 'ReadInt32'},
    'float': {'pack': 'f', 'cs_read': 'ReadSingle'},
    'double': {'pack': 'd', 'cs_read': 'ReadDouble'},
    'bool': {'pack': '?', 'cs_read': 'ReadBoolean'},
    'string': {'pack': None, 'cs_read': None},  # 特殊処理
    'vector2': {'pack': None, 'cs_read': None}, # 特殊処理
    'vector3': {'pack': None, 'cs_read': None}  # 特殊処理
}
    
    code_str = ""
    for data in blackboardData:
        
        
        type_str = data["type"]
        initial = ""
        name_data = data["name"]
        # 型変換
        if type_str in enum_list:
            type_str = f"GameCore.Enums.{type_str}ID"
        elif type_str in class_list:
            type_str = f"GameCore.Classes.{type_str}"
        elif type_str in class_data_id_list:
            type_str = f"GameCore.Tables.{type_str}TableID"
        elif type_str.lower() in TYPE_MAP:
            type_str = type_str.capitalize() if type_str.lower() in ['vector2', 'vector3'] else type_str.lower()
        else:
            type_str = type_str  
            
        # 初期値
        if type_str.lower() in ['int', 'byte', 'short', 'long']:
            initial = '0'
        elif type_str.lower() in ['float', 'double', 'decimal']:
            initial = '0.0'
        elif type_str.lower() == 'bool':
            initial = 'false'
        elif type_str.lower() == 'string' or type_str.lower() == 'char':
            initial = '""'
        elif type_str.lower() == 'vector2':
            initial = 'new Vector2()'
        elif type_str.lower() == 'vector3':
            initial = 'new Vector3()'
        elif type_str.startswith('GameCore.Enums.'):
            initial = f"{type_str}.None"
        elif type_str.startswith('GameCore.Tables.'):
            initial = f"{type_str}.None"
        else:
            initial = f"new {type_str}()"    

        code_str += f"""
        protected {type_str} {name_data} = {initial};
        """
    
    with open(os.path.join(DATA_DIR,BEHAVIOR_DATA,f"{name}",f"Base{name}BehaviorBlackboard.cs"),"w", encoding="utf-8") as f:
        base_str = f"""


namespace GameCore.Behavior
{{
    public class Base{name}BehaviorBlackboard<T>   : BaseBehaviorBlackboard<T, {name}BehaviorID>
        where T : BaseTestNPCBehaviorBlackboard<T>, new()
    {{
{code_str}
    }}
}}
        """
        f.write(base_str)
        
    if not os.path.exists(os.path.join(DATA_DIR,BEHAVIOR_DATA,f"{name}",f"{name}BehaviorBlackboard.cs")):
        with open(os.path.join(DATA_DIR,BEHAVIOR_DATA,f"{name}",f"{name}BehaviorBlackboard.cs"),"w", encoding="utf-8") as f:
            base_str = f"""


namespace GameCore.Behavior
{{
    public class {name}BehaviorBlackboard :  Base{name}BehaviorBlackboard<{name}BehaviorBlackboard>
    {{
    }}
}}
        """
            f.write(base_str)
            
def generate_behavior_tree(data, name):
    nodes = data.get("nodes", {})
    root_id = data.get("root")
    if not root_id or root_id not in nodes:
        return

    # 1. generate_custom_id_code を呼び出し、id_map を取得
    id_map = generate_custom_id_code(data, name)

    output_path = os.path.join(DATA_DIR, BEHAVIOR_DATA, name, f"{name}BehaviorTree.cs")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    build_code = []
    node_var_map = {}  # node_id → 変数名

    def get_node_var(node_id):
        if node_id not in node_var_map:
            safe_id = node_id.replace("-", "_").replace(".", "_")
            node_var_map[node_id] = f"node_{safe_id}"
        return node_var_map[node_id]

    def build_node(node_id,custom_node_map, parent_var=None):
        node = nodes.get(node_id)
        if not node:
            return

        var_name = get_node_var(node_id)
        node_type = node.get("type", "").lower()
        label = node.get("label", node_id)
        children = node.get("children", [])
        resetType = node.get("resetType","None")
        resetTypeName = f"BehaviorResetTypeID.{resetType}"
        enum_id = id_map.get(node_id)
        # === ノード生成 ===
        if node_type in ["root", "sequence"]:
            build_code.append(f"            var {var_name} = new SequenceNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id},{resetTypeName});")
        elif node_type == "selector":
            build_code.append(f"            var {var_name} =  new SelectorNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id},{resetTypeName});")
        elif node_type == "parallel":
            success_policy = node.get("config", {}).get("successPolicy", "ALL")
            failure_policy = node.get("config", {}).get("failurePolicy", "ANY")
            build_code.append(f"            var {var_name} = new ParallelNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id}, ParallelPolicyID.{success_policy}, ParallelPolicyID.{failure_policy},{resetTypeName});")
        elif node_type == "race":
            build_code.append(f"            var {var_name} = new RaceNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id},{resetTypeName});")
        elif node_type == "repeater":
            count = node.get("config", {}).get("count", 3)
            build_code.append(f"            var {var_name} = new RepeaterNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id}, {count},{resetTypeName});")
        elif node_type == "delay":
            sec = node.get("config", {}).get("seconds", 1.0)
            build_code.append(f"            var {var_name} = new DelayNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id}, {sec}f,{resetTypeName});")
        elif node_type == "timeout":
            sec = node.get("config", {}).get("seconds", 5.0)
            build_code.append(f"            var {var_name} = new TimeoutNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id}, {sec}f,{resetTypeName});")
        elif node_type == "inverter":
            build_code.append(f"            var {var_name} = new InverterNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id},{resetTypeName});")
        elif node_type == "failer":
            build_code.append(f"            var {var_name} = new FailerNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id},{resetTypeName});")
        elif node_type == "repeatuntilsuccess":
            build_code.append(f"            var {var_name} = new RepeatUntilSuccessNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id},{resetTypeName});")
        elif node_type == "limiter":
            max_count = node.get("config", {}).get("max", 3)
            build_code.append(f"            var {var_name} = new LimiterNode<{name}BehaviorBlackboard, {name}BehaviorID>({name}BehaviorID.{enum_id}, {max_count},{resetTypeName});")
        elif node_type == "custom":
            if label in custom_node_map:
                type_custom = custom_node_map[label].get("type","")
                custom_name = custom_node_map[label].get("name","")
                if type_custom == "action":
                    class_name = f"{name}{custom_name}ActionNode"
                    build_code.append(f"            var {var_name} = new {class_name}({name}BehaviorID.{enum_id},{resetTypeName});")
                else:
                    class_name = f"{name}{custom_name}ConditionNode"
                    build_code.append(f"            var {var_name} = new {class_name}({name}BehaviorID.{enum_id},{resetTypeName});")

        elif node_type.startswith("blackboard"):
            # 2. id_map から正確な enum_id を取得
            if not enum_id:
                build_code.append(f"        // Warning: enum_id not found for {node_id}")
                return
            build_code.append(f"            var {var_name} = new {name}BlackboardConditionNode({name}BehaviorID.{enum_id},{resetTypeName});")
        else:
            build_code.append(f"        // Unknown node type: {node_type}")
            return

        # 子ノード構築
        for child_id in children:
            build_node(child_id,custom_node_map,var_name)

        # 親に追加
        if parent_var:
            build_code.append(f"            {parent_var}.AddChild({var_name});")

    custom_node_map = {}
    for custom in data.get("customNodes", []):
        custom_node_map[custom["name"]] = custom  # 名前で検索可能
    # ルートから開始
    build_node(root_id,custom_node_map)

    # ツリークラス生成
    root_var = get_node_var(root_id)
    tree_class = f"""using System;
using UnityEngine;

namespace GameCore.Behavior
{{
    public class {name}BehaviorTree : BaseBehaviorTree<{name}BehaviorBlackboard, {name}BehaviorID>
    {{
        public override void OnInit(Action<{name}BehaviorBlackboard> action = null,{name}BehaviorBlackboard blackboard = null)
        {{
            
            if(blackboard != null)
            {{
                SetBlackboard(blackboard);
            }}
            Blackboard.OnInit(action);

            // === ツリー構築 ===
{chr(10).join(build_code)}

            // ルート設定
            SetRoot({root_var});
            Root?.OnInit(Blackboard);
            
        }}

        public override BehaviorResultStatus Tick()
        {{
            if (Root == null) return BehaviorResultStatus.Failure;
            return Root.OnTick(Blackboard);
        }}

        public override void OnReset(Action<{name}BehaviorBlackboard> action = null)
        {{
            Blackboard.OnReset(action);
            Root?.OnReset(Blackboard);
        }}
    }}
}}
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(tree_class)

    print(f"{name}BehaviorTree.cs が生成されました: {output_path}")